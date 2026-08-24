#!/usr/bin/env python3
import argparse
import glob
import json
import os

import cv2
import numpy as np
import rosbag
import sensor_msgs.point_cloud2 as pc2
from cv_bridge import CvBridge


def stamp_to_sec(stamp):
    return float(stamp.secs) + float(stamp.nsecs) * 1e-9


def resolve_bag(path):
    if os.path.isdir(path):
        bags = sorted(glob.glob(os.path.join(path, "*.bag")))
        if not bags:
            raise FileNotFoundError(f"no .bag files in {path}")
        return bags[0]
    return path


def quat_xyzw_to_rot(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    if n == 0.0:
        return np.eye(3, dtype=np.float64)
    s = 2.0 / n
    xx, yy, zz = x * x * s, y * y * s, z * z * s
    xy, xz, yz = x * y * s, x * z * s, y * z * s
    wx, wy, wz = w * x * s, w * y * s, w * z * s
    return np.array(
        [
            [1.0 - yy - zz, xy - wz, xz + wy],
            [xy + wz, 1.0 - xx - zz, yz - wx],
            [xz - wy, yz + wx, 1.0 - xx - yy],
        ],
        dtype=np.float64,
    )


def load_calib(path):
    with open(path, "r") as f:
        config = json.load(f)

    results = config.get("results", {})
    key = None
    for candidate in ("T_lidar_camera", "init_T_lidar_camera", "init_T_lidar_camera_auto"):
        if candidate in results:
            key = candidate
            break
    if key is None:
        raise KeyError("calib.json has no T_lidar_camera or initial guess transform")

    values = np.asarray(results[key], dtype=np.float64)
    t_lidar_camera = values[:3]
    r_lidar_camera = quat_xyzw_to_rot(values[3:7])

    r_camera_lidar = r_lidar_camera.T
    t_camera_lidar = -r_camera_lidar @ t_lidar_camera

    fx, fy, cx, cy = config["camera"]["intrinsics"]
    camera_matrix = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)
    dist_coeffs = np.asarray(config["camera"].get("distortion_coeffs", []), dtype=np.float64)
    return key, r_camera_lidar, t_camera_lidar, camera_matrix, dist_coeffs


def read_first_pair(bag_path, image_topic, points_topic):
    bridge = CvBridge()
    image_msg = None
    image_stamp = None
    clouds = []

    with rosbag.Bag(bag_path, "r") as bag:
        for topic, msg, _ in bag.read_messages(topics=[image_topic, points_topic]):
            if topic == image_topic and image_msg is None:
                image_msg = msg
                image_stamp = stamp_to_sec(msg.header.stamp)
            elif topic == points_topic:
                clouds.append(msg)

            if image_msg is not None and len(clouds) >= 3:
                break

    if image_msg is None:
        raise RuntimeError(f"no image message on {image_topic}")
    if not clouds:
        raise RuntimeError(f"no point cloud message on {points_topic}")

    cloud_msg = min(clouds, key=lambda msg: abs(stamp_to_sec(msg.header.stamp) - image_stamp))
    image = bridge.imgmsg_to_cv2(image_msg, desired_encoding="bgr8")
    return image, image_stamp, cloud_msg, stamp_to_sec(cloud_msg.header.stamp)


def cloud_to_array(msg, max_points):
    field_names = [field.name for field in msg.fields]
    fields = ["x", "y", "z"]
    has_intensity = "intensity" in field_names
    if has_intensity:
        fields.append("intensity")

    rows = []
    for point in pc2.read_points(msg, field_names=fields, skip_nans=True):
        rows.append(point)

    if not rows:
        raise RuntimeError("point cloud has no finite points")

    arr = np.asarray(rows, dtype=np.float64)
    if max_points > 0 and arr.shape[0] > max_points:
        idx = np.linspace(0, arr.shape[0] - 1, max_points).astype(np.int64)
        arr = arr[idx]
    return arr[:, :3], arr[:, 3] if has_intensity else None


def draw_overlay(
    image,
    points_lidar,
    intensities,
    r_camera_lidar,
    t_camera_lidar,
    camera_matrix,
    dist_coeffs,
    point_radius,
    image_alpha,
    point_alpha,
):
    points_camera = (r_camera_lidar @ points_lidar.T).T + t_camera_lidar.reshape(1, 3)
    in_front = points_camera[:, 2] > 0.1
    points_lidar = points_lidar[in_front]
    points_camera = points_camera[in_front]
    if intensities is not None:
        intensities = intensities[in_front]

    rvec, _ = cv2.Rodrigues(r_camera_lidar)
    tvec = t_camera_lidar.reshape(3, 1)
    image_points, _ = cv2.projectPoints(points_lidar.astype(np.float64), rvec, tvec, camera_matrix, dist_coeffs)
    image_points = image_points.reshape(-1, 2)
    finite = np.isfinite(image_points).all(axis=1)
    image_points = image_points[finite]
    points_camera = points_camera[finite]
    if intensities is not None:
        intensities = intensities[finite]

    height, width = image.shape[:2]
    inside = (image_points[:, 0] >= 0.0) & (image_points[:, 0] < width) & (image_points[:, 1] >= 0.0) & (image_points[:, 1] < height)
    u = np.round(image_points[:, 0][inside]).astype(np.int32)
    v = np.round(image_points[:, 1][inside]).astype(np.int32)
    depths = points_camera[:, 2][inside]

    if intensities is not None:
        color_values = intensities[inside]
    else:
        color_values = depths

    if color_values.size == 0:
        return image.copy(), 0

    lo, hi = np.percentile(color_values, [2, 98])
    scale = np.clip((color_values - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    colors = cv2.applyColorMap((scale * 255.0).astype(np.uint8), cv2.COLORMAP_TURBO).reshape(-1, 3)

    overlay = np.zeros_like(image)
    order = np.argsort(depths)[::-1]
    for idx in order:
        cv2.circle(overlay, (int(u[idx]), int(v[idx])), point_radius, colors[idx].tolist(), -1, lineType=cv2.LINE_AA)

    background = cv2.addWeighted(image, image_alpha, np.zeros_like(image), 1.0 - image_alpha, 0.0)
    blended = cv2.addWeighted(background, 1.0, overlay, point_alpha, 0.0)
    return blended, int(len(u))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True)
    parser.add_argument("--calib", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--image-topic", default="/roof_clpe_ros/roof_cam_1/image_raw")
    parser.add_argument("--points-topic", default="/lidar0/velodyne_points")
    parser.add_argument("--max-points", type=int, default=80000)
    parser.add_argument("--point-radius", type=int, default=2)
    parser.add_argument("--image-alpha", type=float, default=0.35)
    parser.add_argument("--point-alpha", type=float, default=1.0)
    args = parser.parse_args()

    bag_path = resolve_bag(args.bag)
    key, r_camera_lidar, t_camera_lidar, camera_matrix, dist_coeffs = load_calib(args.calib)
    image, image_stamp, cloud_msg, cloud_stamp = read_first_pair(bag_path, args.image_topic, args.points_topic)
    points, intensities = cloud_to_array(cloud_msg, args.max_points)
    overlay, count = draw_overlay(
        image,
        points,
        intensities,
        r_camera_lidar,
        t_camera_lidar,
        camera_matrix,
        dist_coeffs,
        args.point_radius,
        args.image_alpha,
        args.point_alpha,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    cv2.imwrite(args.output, overlay)

    print(f"bag: {bag_path}")
    print(f"transform: {key}")
    print(f"image_stamp: {image_stamp:.6f}")
    print(f"cloud_stamp: {cloud_stamp:.6f}")
    print(f"projected_points: {count}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
