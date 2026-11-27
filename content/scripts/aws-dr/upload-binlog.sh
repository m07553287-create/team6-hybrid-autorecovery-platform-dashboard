#!/usr/bin/env bash
# 원본: aws-dr /home/rocky/minwon-backup/upload-binlog.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -Eeuo pipefail
SRC=/var/backups/minwon/incoming/binlog/
DEST=s3://<백업-버킷>/minwon-db/binlog/
exec 9>/home/rocky/minwon-backup/upload.lock
flock -n 9 || exit 1
aws s3 sync "$SRC" "$DEST" --exclude "*" --include "binlog.*" --region ap-northeast-2 --sse AES256 --only-show-errors
echo "S3 Binlog 동기화 완료"
