FROM grafana/grafana:12.1.0
LABEL org.opencontainers.image.title="job-aggregator-grafana"
# Datasource and dashboards are loaded from files at start-up: nothing to click.
COPY provisioning /etc/grafana/provisioning
COPY dashboards /var/lib/grafana/dashboards
