"""backend Lambda 실코드 패키징 — 스텁→실코드 스왑의 '빌드' 절반. (2026-07-03 신설)

무엇을 만드나 (전부 infra/backend/build/ 아래, .gitignore 대상):
  src-pipeline/   = pipeline/ + contracts/*.json   → ingest·normalize Lambda zip 소스
  src-attackpath/ = attackpath/ + contracts/*.json → correlation Lambda zip 소스
  src-engine/     = engine/ + contracts/*.json     → orchestrator·remediation Lambda zip 소스
  layer/python/   = psycopg2-binary(manylinux x86_64, cp312) → Lambda 레이어 zip 소스

왜 이 구조인가:
  - 각 패키지의 데이터파일 경로 해석이 전부 "zip루트/contracts/"를 가리킴
    (normalizer._CATALOG_PATH = __file__../../../contracts, engine.core.contracts = __file__../../contracts)
    → 패키지와 contracts를 zip 루트에 나란히 두면 코드 무변경으로 동작.
  - psycopg2는 C 확장이라 Windows/맥에서 pip install한 걸 그대로 zip하면 Lambda(리눅스)에서 import 실패.
    pip의 --platform manylinux2014_x86_64 --only-binary 조합으로 '리눅스용 휠'을 어느 OS에서든 받아온다.
  - zip 자체는 terraform archive_file이 만든다(소스 해시 일관성) — 이 스크립트는 디렉터리만 준비.

실행: python infra/backend/build_lambdas.py   (infra/deploy.ps1이 backend apply/plan 전에 자동 실행)
검증: 각 번들에 핸들러 파일 존재 + 레이어에 psycopg2/ 존재를 assert — 실패 시 exit 1(배포 차단).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 가드(레포 컨벤션)

HERE = Path(__file__).resolve().parent          # infra/backend
ROOT = HERE.parent.parent                       # 레포 루트
BUILD = HERE / "build"

# 번들 정의: (빌드 폴더명, 포함 패키지, 배포 후 존재해야 할 핸들러 파일)
BUNDLES = [
    ("src-pipeline", "pipeline", ["pipeline/ingest/handler.py", "pipeline/normalize/handler.py"]),
    ("src-attackpath", "attackpath", ["attackpath/correlation/handler.py"]),
    ("src-engine", "engine", ["engine/handler.py", "engine/remediation.py"]),
]

# 패키지 복사에서 제외 — 캐시·데모 산출물(런타임 불필요, zip 슬림 유지)
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "out_case.json")


def build_bundles() -> None:
    for name, pkg, handlers in BUNDLES:
        dst = BUILD / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(ROOT / pkg, dst / pkg, ignore=IGNORE)
        # contracts는 *.json만(스키마·카탈로그·mock — 런타임 로드 대상). validate.py 등 스크립트 제외.
        (dst / "contracts").mkdir(parents=True, exist_ok=True)
        for j in (ROOT / "contracts").glob("*.json"):
            shutil.copy2(j, dst / "contracts" / j.name)
        for h in handlers:
            assert (dst / h).is_file(), f"[{name}] 핸들러 누락: {h}"
        n = sum(1 for _ in dst.rglob("*") if _.is_file())
        print(f"OK {name}: {n} files (pkg={pkg} + contracts/*.json)")


def build_psycopg2_layer() -> None:
    """리눅스(manylinux x86_64)·py3.12용 psycopg2-binary를 레이어 규격(python/ 하위)으로 설치."""
    target = BUILD / "layer" / "python"
    if (BUILD / "layer").exists():
        shutil.rmtree(BUILD / "layer")
    target.mkdir(parents=True)
    cmd = [
        sys.executable, "-m", "pip", "install", "psycopg2-binary",
        "--platform", "manylinux2014_x86_64",   # Lambda(리눅스 x86_64)용 휠 강제
        "--implementation", "cp", "--python-version", "3.12",
        "--only-binary=:all:",                  # 소스빌드 금지(로컬 OS 오염 방지)
        "--target", str(target), "--quiet",
    ]
    subprocess.run(cmd, check=True)
    assert (target / "psycopg2").is_dir(), "psycopg2 레이어 설치 실패"
    print(f"OK layer: psycopg2-binary (manylinux2014_x86_64, cp312) -> {target}")


def build_xray_layer() -> None:
    """aws-xray-sdk(순수 파이썬, C 확장 없음 — psycopg2와 달리 --platform 불요)를 별도 레이어로.
    5개 Lambda(ingest·normalize·correlation·orchestrator·remediation) 전부가 X-Ray 분산 트레이싱용으로 부착.

    ⚠️ --no-deps 필수: aws-xray-sdk의 기본 설치는 botocore/boto3/urllib3까지 통째로 딸려와서(30MB+)
    레이어가 불필요하게 커지고, Lambda 런타임이 이미 제공하는 botocore와 버전이 달라 섀도잉될 위험이
    있다(patch()는 '이미 임포트된' botocore를 몽키패치하는 것이지 자체 botocore가 필요한 게 아님).
    실제 필요한 건 순수 패칭 의존성인 wrapt뿐.
    """
    target = BUILD / "layer-xray" / "python"
    if (BUILD / "layer-xray").exists():
        shutil.rmtree(BUILD / "layer-xray")
    target.mkdir(parents=True)
    cmd = [
        sys.executable, "-m", "pip", "install", "aws-xray-sdk", "wrapt",
        "--no-deps", "--target", str(target), "--quiet",
    ]
    subprocess.run(cmd, check=True)
    assert (target / "aws_xray_sdk").is_dir(), "aws-xray-sdk 레이어 설치 실패"
    assert (target / "wrapt").is_dir(), "wrapt(aws-xray-sdk 의존성) 설치 실패"
    print(f"OK layer: aws-xray-sdk(+wrapt, --no-deps로 botocore 재번들 회피) -> {target}")


if __name__ == "__main__":
    BUILD.mkdir(exist_ok=True)
    build_bundles()
    build_psycopg2_layer()
    build_xray_layer()
    print("BUILD DONE - terraform(archive_file)이 이 디렉터리들을 zip합니다.")
