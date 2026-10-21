# Reconstructed from the build history of the amr-cluster-meeting:latest image.
FROM python:3.11-slim
RUN pip install --no-cache-dir numpy pandas
WORKDIR /app
COPY generate_cluster_meeting.py /app/generate_cluster_meeting.py
ENTRYPOINT ["python", "/app/generate_cluster_meeting.py"]
CMD ["--input", "/outputs/activity_exploration", "--out", "/outputs/cluster_meeting"]
