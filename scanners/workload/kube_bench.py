"""kube-bench KSPM 스캐너 (진우 담당) — CIS Kubernetes 벤치마크 → 계약⑤ ingest-envelope.

역할:
  kube-bench(aquasecurity)로 EKS 노드/클러스터의 CIS 벤치마크를 점검하고,
  결과를 계약⑤ ingest-envelope으로 감싸 반환한다.
  이후 Normalizer(pipeline/normalize)가 envelope → 계약① finding 변환.

⚠️ 모델링 단순화(문서화, control-catalog.json 참고): kube-bench는 원래
   노드/클러스터 스코프 도구라 특정 파드를 지목하지 않는다(같은 control의
   대체 소스 "trivy-k8s:KSV*"가 실제로는 파드별 매니페스트 스캔에 더 적합).
   골든 시나리오(파드별 Pod Security 위반, f2·f13)를 재현하기 위해 "이 점검
   실행이 어떤 워크로드를 대표하는가"를 호출자가 `target` 파라미터로 지정하는
   방식으로 데모 단순화했다 — Trivy가 `image`를 파라미터로 받는 것과 동일한
   패턴. 실 배포에서는 노드별 스캔 결과를 그 노드에서 도는 파드 목록에
   매핑하는 별도 로직이 있어야 완전히 정확하다.

흐름:
  KubeBenchScanner.scan_from_json(kube_bench_json, target="shop/product")
      └─ _build_envelope(raw_json, target) → 계약⑤ envelope(source="kube-bench")

실배포 스왑:
  KubeBenchScanner.scan_cluster(target="shop/product") — kubectl로 공식
  kube-bench Job(aquasecurity 패턴)을 배포해 CIS 벤치마크 실행 → JSON 로그
  회수 → envelope. 전제: EKS kubeconfig 설정 완료(infra apply 후, read-only면
  충분 — kube-bench 자체는 호스트 설정 파일을 읽기만 함).

목업용:
  scan_from_json(kube_bench_json, target) — kubectl/kube-bench 없이 JSON 직접 주입.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Optional


class KubeBenchScanError(Exception):
    """kube-bench 실행 실패(kubectl 미설치·클러스터 미접속·Job 타임아웃 등)."""


class KubeBenchScanner:
    """kube-bench CIS Kubernetes 벤치마크 스캐너 래퍼.

    EKS 클러스터에 kubectl로 접속 가능한 환경에서는 scan_cluster()로 실 스캔
    (⚠️ EKS 미apply 상태라 미검증 — Trivy.scan_image()와 동일한 처지).
    CI/테스트에서는 scan_from_json()으로 미리 받아둔 JSON을 봉투화.
    """

    def __init__(self, kubectl_bin: str = "kubectl", namespace: str = "kube-bench") -> None:
        self._kubectl = kubectl_bin
        self._namespace = namespace

    # ── 실 스캔 (kubectl + 실 EKS 클러스터 필요) ─────────────────────────

    def scan_cluster(
        self,
        target: str,
        node_selector: Optional[str] = None,
        timeout: int = 180,
    ) -> dict:
        """공식 kube-bench Job을 배포해 CIS 벤치마크 실행 → 계약⑤ ingest-envelope.

        Args:
            target:        이 스캔 실행이 대표하는 워크로드(예: "shop/product") —
                           resource_id 캐논화에 쓰임(모듈 docstring의 모델링 단순화).
            node_selector: 특정 노드에서만 실행하려면 "key=value" 지정(선택).
            timeout:       Job 완료 대기 최대 시간(초).

        Returns:
            계약⑤ ingest-envelope dict (raw_inline = kube-bench JSON 원본 + target_resource)

        Raises:
            KubeBenchScanError: kubectl 미설치, Job 배포/완료대기/로그회수 실패
        """
        job_name = "kube-bench-%s" % _now_batch()
        manifest = _job_manifest(job_name, self._namespace, node_selector)
        try:
            self._kubectl_run(["apply", "-f", "-"], input_text=manifest, timeout=timeout)
            self._kubectl_run(
                [
                    "wait", "--for=condition=complete", "--timeout=%ds" % timeout,
                    "job/%s" % job_name, "-n", self._namespace,
                ],
                timeout=timeout + 10,
            )
            raw_text = self._kubectl_run(
                ["logs", "job/%s" % job_name, "-n", self._namespace], timeout=timeout,
            )
        finally:
            # 정리는 베스트에포트 — 실패해도 스캔 결과 자체는 이미 확보됐으면 무시.
            self._kubectl_run(
                ["delete", "job", job_name, "-n", self._namespace, "--ignore-not-found"],
                timeout=timeout, check=False,
            )
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise KubeBenchScanError("kube-bench 출력 JSON 파싱 실패: %s" % e)
        return self._build_envelope(raw, target)

    def _kubectl_run(
        self, args, input_text: Optional[str] = None, timeout: int = 180, check: bool = True,
    ) -> str:
        cmd = [self._kubectl] + args
        try:
            result = subprocess.run(
                cmd, input=input_text, capture_output=True, text=True, timeout=timeout,
            )
        except FileNotFoundError:
            raise KubeBenchScanError(
                "kubectl을 찾을 수 없음. EKS kubeconfig 설정 후 재시도"
                "(aws eks update-kubeconfig --name <cluster>)."
            )
        except subprocess.TimeoutExpired:
            raise KubeBenchScanError("kubectl 타임아웃(%ds): %s" % (timeout, " ".join(args)))
        if check and result.returncode != 0:
            raise KubeBenchScanError(
                "kubectl 실패(exit %d): %s" % (result.returncode, result.stderr[:500])
            )
        return result.stdout

    # ── 목업용 ────────────────────────────────────────────────────────

    def scan_from_json(self, kube_bench_json: dict, target: str) -> dict:
        """미리 받아둔 kube-bench JSON을 계약⑤ ingest-envelope으로 감싸기.

        kube-bench/kubectl 없이 run_demo / CI에서 end-to-end 흐름을 검증할 때 사용.
        """
        return self._build_envelope(kube_bench_json, target)

    # ── 봉투화 ────────────────────────────────────────────────────────

    def _build_envelope(self, raw: dict, target: str) -> dict:
        """계약⑤ ingest-envelope 조립.

        source="kube-bench"(계약⑤ enum에 이미 정의됨), source_format="custom"
        — kube-bench 고유 스키마라 기존 asff/ocsf/prowler-json/trivy-json
        어디에도 안 맞음(정규화부가 source=="kube-bench"로 분기, pipeline/
        normalize/normalizer.py의 _parse_kube_bench 참고).
        raw_inline에 target_resource를 얹어 정규화부에 파드 귀속 정보를
        전달한다(모듈 docstring의 모델링 단순화 — 원본을 변형하지 않도록
        raw는 얕은 복사).
        """
        raw_with_target = dict(raw)
        raw_with_target["target_resource"] = target
        safe_target = target.replace("/", "-")
        return {
            "envelope_id": str(uuid.uuid4()),
            "source": "kube-bench",
            "source_format": "custom",
            "cloud_hint": "aws",
            "scan_batch_id": "kube-bench-%s-%s" % (safe_target, _now_batch()),
            "ingested_at": _now(),
            "raw_inline": raw_with_target,
        }


# ── kube-bench Job 매니페스트(aquasecurity 공식 job-eks.yaml 패턴 축약) ──

def _job_manifest(job_name: str, namespace: str, node_selector: Optional[str]) -> str:
    node_selector_yaml = ""
    if node_selector:
        key, _, value = node_selector.partition("=")
        node_selector_yaml = (
            "      nodeSelector:\n"
            '        %s: "%s"\n' % (key, value)
        )
    return """apiVersion: batch/v1
kind: Job
metadata:
  name: {job_name}
  namespace: {namespace}
spec:
  backoffLimit: 0
  template:
    spec:
      hostPID: true
{node_selector}      containers:
        - name: kube-bench
          image: aquasec/kube-bench:latest
          command: ["kube-bench", "run", "--targets", "node,policies", "--json"]
          volumeMounts:
            - {{name: var-lib-kubelet, mountPath: /var/lib/kubelet, readOnly: true}}
            - {{name: etc-systemd, mountPath: /etc/systemd, readOnly: true}}
            - {{name: etc-kubernetes, mountPath: /etc/kubernetes, readOnly: true}}
      restartPolicy: Never
      volumes:
        - name: var-lib-kubelet
          hostPath: {{path: /var/lib/kubelet}}
        - name: etc-systemd
          hostPath: {{path: /etc/systemd}}
        - name: etc-kubernetes
          hostPath: {{path: /etc/kubernetes}}
""".format(job_name=job_name, namespace=namespace, node_selector=node_selector_yaml)


# ── 헬퍼 ──────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_batch() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


# ── CLI 간이 사용 (python -m scanners.workload.kube_bench <target>) ─────

def _cli_main() -> int:
    import sys
    if len(sys.argv) < 2:
        print("사용법: python -m scanners.workload.kube_bench <target>", file=sys.stderr)
        return 1
    target = sys.argv[1]
    scanner = KubeBenchScanner()
    try:
        envelope = scanner.scan_cluster(target)
    except KubeBenchScanError as e:
        print("오류:", e, file=sys.stderr)
        return 1

    print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
