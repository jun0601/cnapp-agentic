# order 서비스 = AWS retail-store-sample-app의 orders 서비스 자리(upstream fork).
# order의 의도적 결함(f5 = 평문 Azure SP 자격증명)은 이미지가 아니라 k8s 매니페스트의 env에 있으므로,
# 이미지는 "스캔 대상 워크로드가 존재"하게만 하면 되는 placeholder(keep-alive)면 충분하다.
# 실배포 시 upstream retail-store orders 이미지로 교체.
FROM public.ecr.aws/docker/library/amazonlinux:2023
WORKDIR /app

EXPOSE 8080
# placeholder keep-alive.
# 주의: exec-form(JSON 배열) 뒤에 인라인 주석을 붙이면 Docker가 shell-form으로 폴백해 크래시한다
#       (product Dockerfile에서 라이브로 실측한 함정). 그래서 주석은 반드시 이 윗줄에 둔다.
CMD ["sleep", "infinity"]
