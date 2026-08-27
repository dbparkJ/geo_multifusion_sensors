# Geo Multi-Fusion Sensors — Legacy Repository

> **신규 개발 중단:** 이 저장소의 기능은
> [`geonLabs/geonova-depthai-mapper`](https://github.com/geonLabs/geonova-depthai-mapper)로
> 통합되었습니다. 새로운 기능, 버그 수정, Jetson 배포는 기준 저장소에서만 진행합니다.

## 단일 기준 저장소

```text
Canonical: geonLabs/geonova-depthai-mapper
Legacy:    dbparkJ/geo_multifusion_sensors
```

이 저장소는 과거 커밋과 기존 장비의 재현을 위한 이력 보관용입니다.
`safe_gard_test/code`를 수정하거나 기준 저장소의 코드를 다시 복사하지 않습니다.

## 이전된 기능

| 기존 경로 | 기준 저장소 경로 |
|---|---|
| `safe_gard_test/code/` | `code/` |
| `safe_gard_test/model/` | `model/` |
| `test/convert_lidar_bag_to_pcd.py` | `tools/lidar/convert_lidar_bag_to_pcd.py` |
| `test/config.yaml` | `tools/lidar/config.yaml` |
| `test/requirements.txt` | `tools/lidar/requirements.txt` |
| `scripts/project_lidar_overlay.py` | `tools/lidar/project_lidar_overlay.py` |

기준 저장소에는 다음 운영 개선도 포함되어 있습니다.

- 데이터셋을 생성하지 않는 `--monitor-only`
- OAK 장애 시 GPS/IMU를 유지하는 카메라 재연결
- `/dev/serial/by-id` 기반 GNSS/EBIMU 안전 자동 탐색
- 이동 중 NTRIP 기준국 make-before-break 전환
- 동일 초 재시작 시 기존 데이터셋 덮어쓰기 방지
- LiDAR 변환 회귀 테스트와 GitHub Actions

## 기존 장비 이전

기존 폴더 위에 새 코드를 덮어쓰지 말고 기준 저장소를 별도로 clone합니다.

```bash
cd ~
git clone https://github.com/geonLabs/geonova-depthai-mapper.git
cd geonova-depthai-mapper
chmod +x install.sh
./install.sh --dev
```

Jetson Controller에는 새 저장소 폴더를 다시 등록해야 새 release snapshot이 적용됩니다.
기존 수집 데이터, `.venv`, 대형 모델 가중치는 Git 저장소 사이에 복사하지 말고 외부
데이터 경로 또는 배포 절차로 연결합니다.

LiDAR 도구는 기준 저장소에서 별도 환경을 사용합니다.

```bash
cd geonova-depthai-mapper/tools/lidar
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## 자격증명

공유 `config.yaml`에는 NTRIP 계정이나 비밀번호를 기록하지 않습니다.
`NTRIP_USERNAME`, `NTRIP_PASSWORD` 환경변수 또는 Jetson Controller의 보호 환경
설정을 사용합니다.

과거 커밋에 들어간 인증정보는 파일 삭제만으로 보호되지 않습니다. 기존 자격증명을
폐기하고 새 값으로 발급한 뒤 기준 저장소의 보호 환경에 다시 등록해야 합니다.

## 유지 정책

- 이 저장소에는 신규 기능을 추가하지 않습니다.
- 긴급 이력 복구 외에는 PR을 만들지 않습니다.
- 문서와 이슈는 기준 저장소로 연결합니다.
- 향후 저장소 설정에서 Archive 처리가 가능해지면 읽기 전용으로 전환합니다.
