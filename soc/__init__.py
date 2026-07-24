"""SOC 확장 훅 (범위 밖) — GuardDuty 런타임 위협 탐지 독립 데모.

이 패키지는 핵심 CNAPP 파이프라인과 **완전히 분리**돼 있다:
  - contracts/ 계약 스키마 미접촉 (SOC event는 CNAPP finding과 별도 모델)
  - pipeline/normalize · RDS · control-catalog · console 미접촉

배경·스코프 판단·실증 기록은 soc/README.md 참조.
"""
