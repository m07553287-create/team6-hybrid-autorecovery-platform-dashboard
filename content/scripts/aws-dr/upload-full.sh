#!/bin/bash
# 원본: aws-dr /home/rocky/minwon-backup/upload-full.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
aws s3 sync /var/backups/minwon/incoming/full/ s3://<백업-버킷>/minwon-db/full/ --exclude "*" --include "minwon-*.sql.gz" --region ap-northeast-2 --sse AES256 --only-show-errors
echo "S3 Full Backup 동기화 완료"
