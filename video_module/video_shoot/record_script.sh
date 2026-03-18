#!/bin/bash
ffmpeg -f x11grab -video_size 1920x1080 -i :0.0 -c:v libx264 -preset ultrafast -pix_fmt yuv420p /root/project/ai_video/video_module/video_shoot/视频_20260318_1820.mp4 &
PID=$!
sleep 180
kill $PID
