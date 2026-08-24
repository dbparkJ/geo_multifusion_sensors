# Geo Multi-Fusion Sensors

OAK RGB-D, GPS/RTK, 내·외부 IMU 수집과 방호울타리 YOLO segmentation/지도
선형화, ROS1 bag의 LiDAR–카메라 추출·투영 도구를 한 저장소에서 관리합니다.

## Jetson Controller 자동 실행 폴더

저장소 루트는 JetsonControllerApp의 Python 작업 폴더 계약을 따릅니다.

```text
main.py                      관리형 수집 진입점
config.yaml                  이식 가능한 수집 기본값
.venv/                       install.sh가 만드는 실제 가상환경(Git 제외)
results/                     수집 결과와 controller bridge 상태(Git 제외)
safe_gard_test/code/         DepthAI 수집·동기화·매핑 구현
```

Controller의 `--folder` 등록은 폴더 이름을 작업 ID로 사용하므로 폴더 이름에는
소문자, 숫자, 점, 하이픈, 밑줄만 사용할 수 있습니다. 기본 GitHub 저장소 이름을
그대로 clone해 등록할 수 있습니다.

```bash
git clone https://github.com/dbparkJ/geo_multifusion_sensors.git
cd geo_multifusion_sensors
chmod +x install.sh
./install.sh --dev
```

등록 시 Controller는 `main.py --config <release>/config.yaml`을 실행합니다.
`JETSON_PIPELINE_RESULTS_DIR`가 있으면 `main.py`가 YAML이나 기존 인자보다 뒤에
`--output-dir`을 추가해 승인된 쓰기 경로를 강제합니다. 이때 센서 bridge는
`JETSON_PIPELINE_SENSOR_BRIDGE_DIR`가 있으면 그 경로를 사용하고, 없으면 관리
결과 폴더 아래 `controller-bridge/`에 둡니다. 두 환경변수가 모두 없는 explicit
preset 실행은 기존 CLI/YAML의 bridge 경로를 보존합니다. 루트 `config.yaml`의
기본 경로에서는 `results/controller-bridge/`에 `status.json`과
`camera-preview.jpg`를 기록합니다.

```bash
sudo /opt/jetson-control/register-pipeline.py \
  --folder "$PWD" \
  --name "Geo Multi-Fusion Capture" \
  --user "$(id -un)" \
  --autostart
```

직접 실행할 때도 같은 portable 설정을 사용할 수 있습니다.

```bash
.venv/bin/python main.py --config config.yaml
```

NTRIP 계정은 Git에 기록하지 않습니다. 자동 실행 환경에서는 Controller가 관리하는
보호된 환경 설정으로 `NTRIP_USERNAME`, `NTRIP_PASSWORD`를 주입해야 합니다.
GPS/EBIMU 직렬 포트와 OAK USB 장치에 접근할 수 있도록 pipeline 사용자의 장치
그룹·udev 규칙도 장비에서 확인해야 합니다.

수집 프로세스는 `SIGINT`와 `SIGTERM`을 받으면 pending 이미지 기록을 마치고 CSV와
metadata를 닫습니다. Controller는 소스 snapshot을 실행하므로 코드를 바꾼 뒤에는
pipeline을 다시 등록해야 새 release가 적용됩니다.

## DepthAI 파이프라인

세부 설치, 장치 검증, 수집, 동기화, YOLO/SHP 절차는
[`safe_gard_test/README.md`](safe_gard_test/README.md)와
[`safe_gard_test/code/README.md`](safe_gard_test/code/README.md)를 참고하세요.
YOLO 가중치는 이 통합 저장소에서 제외되므로 실행 전
`safe_gard_test/model/n_model/best.pt` 또는 설정에 지정한 모델을 별도로
준비해야 합니다.

## LiDAR 도구

- `test/convert_lidar_bag_to_pcd.py`: `test/config.yaml`에 따라 ROS1 bag의 LiDAR
  PointCloud2와 가장 가까운 카메라 프레임을 PCD/이미지로 추출합니다.
- `scripts/project_lidar_overlay.py`: ROS 환경에서 calibration JSON을 읽어 첫
  LiDAR–카메라 쌍의 투영 overlay를 만듭니다.

LiDAR bag 변환 도구의 별도 의존성은 `test/requirements.txt`에 있습니다.

## 회귀 테스트

하드웨어를 열지 않는 회귀 테스트는 다음처럼 실행합니다.

```bash
.venv/bin/python -m pytest -q
```
