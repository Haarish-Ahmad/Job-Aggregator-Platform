FROM grafana/grafana:12.1.0
LABEL org.opencontainers.image.title="job-aggregator-grafana"
# Datasource and dashboards are loaded from files at start-up: nothing to click.
COPY provisioning /etc/grafana/provisioning
# Not under /var/lib/grafana: that is the data volume, which would hide these files after the first start and
# stop dashboard updates from ever reaching an existing deployment.
COPY dashboards /etc/grafana/dashboards
