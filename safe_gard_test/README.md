# Geonova DepthAI Mapper

OAK RGB-D, GPS/RTK, 내장·외부 IMU를 동기 수집하고 YOLO segmentation 결과를
지도 좌표의 방호울타리 선형으로 변환하는 프로젝트입니다. 저장소 구조는 현장
작업 폴더와 동일하게 `code/`, `model/`, `data/`로 나눕니다.

```text
code/                         수집·동기화·캘리브레이션·매핑 애플리케이션
model/                        학습·라벨 변환 코드와 로컬 모델 배치 위치
  n_model/best.pt             로컬에서 준비할 guardrail YOLO26n-seg 모델
  x_model/                    대형 현장 모델을 로컬에 두는 위치
data/                         원시/동기 데이터셋(README 외에는 Git 제외)
install.sh, install.ps1       code/.venv 설치 진입점
```

## 설치

Linux/macOS에서는 저장소 루트에서 실행합니다.

```bash
chmod +x install.sh
./install.sh --dev
```

Windows PowerShell에서는 다음을 실행합니다.

```powershell
.\install.ps1 --dev
```

설치기는 Python 3.11 가상환경을 `code/.venv`에 만들고 CUDA Toolkit을 감지해
PyTorch 빌드를 선택합니다.

상위 `geo_multifusion_sensors` 저장소는 가중치 중복을 피하려고
`model/n_model/best.pt`도 Git에서 제외합니다. YOLO 실행 전 현재 mapper 저장소의
소형 모델이나 별도 배포 가중치를 이 경로에 복사해야 합니다.

## 수집과 매핑

```bash
cd code
.venv/bin/python synced_image_recorder.py --config configs/capture.yaml
.venv/bin/python build_synced_dataset.py --config configs/sync.yaml
.venv/bin/python tests/test_yolo_seg_shp.py
.venv/bin/python -m geonova_depthai.debug_ui --config configs/debug_ui.yaml
```

설정 YAML의 상대 경로는 `code` 기준으로 저장소 루트의 `data/`와 `model/`을
가리킵니다. 현장별 경로와 파라미터는 `configs/*.local.yaml`에 두면 Git에
포함되지 않습니다.
YOLO 검출과 SHP 선형화 일괄 실행은 스크립트와 같은 디렉터리의
`code/tests/config.yaml`을 자동으로 읽습니다. YOLO가 만든 `points.csv`로 SHP만
다시 만들 때는 `code` 디렉터리에서 다음 명령을 실행하면
`code/geonova_depthai/config.yaml`을 자동으로 읽습니다.

```bash
.venv/bin/python -m geonova_depthai.fence_linearization
```

다른 YAML을 사용하려면 각 명령에 `--config <경로>`를 지정합니다. YAML의 상대
경로를 일관되게 해석하려면 두 명령 모두 `code` 디렉터리에서 실행하세요.
전체 수집·검증·선형화 절차는 [`code/README.md`](code/README.md)를 참고하세요.

## 학습과 로컬 모델

```bash
code/.venv/bin/python model/convert_label.py --help
code/.venv/bin/python model/safe_gard_train.py \
  --config model/safe_gard_train_config.yaml
```

`model/safe_gard_train_config.yaml`은 로컬 단일 GPU 설정이고,
`model/safe_gard_train_config.4gpu.yaml`은 4-GPU YOLO26x 예시입니다.
`model/x_model/best.pt`처럼 GitHub 일반 파일 제한(100 MiB)을 넘는 가중치는
로컬에 보존하며 커밋하지 않습니다. 배포가 필요하면 Git LFS 또는 Release
asset을 별도로 사용하세요.

## 자격증명

NTRIP 계정은 코드나 공유 YAML에 넣지 않고 `NTRIP_USERNAME`,
`NTRIP_PASSWORD` 환경변수 또는 Git에서 제외되는 `*.local.yaml`로 제공합니다.
