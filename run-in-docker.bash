#!/usr/bin/env bash
#
# shellcheck disable=SC3040
set -euxo pipefail

function main() {
    local current_dir
    current_dir="$(dirname "$0")"

    local action="${1:-}"

    if [  "${action}" = "help" ]; then
        echo "Usage: $0 [headless|stop|help]"
        exit 0
    fi

    local path_to_docker_compose_file
    path_to_docker_compose_file="$(realpath "${current_dir}/docker/docker-compose.yaml")"

    if [ "${action}" = "stop" ]; then
        docker compose -f "${path_to_docker_compose_file}" down
        exit 0
    fi

    docker compose -f "${path_to_docker_compose_file}" build --parallel
    docker compose -f "${path_to_docker_compose_file}" down
    docker compose -f "${path_to_docker_compose_file}" up -d
    local web_container
    web_container="$(docker compose -f "${path_to_docker_compose_file}" ps --format '{{.Name}}' web)"
    local web_container_ip
    web_container_ip=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${web_container}")
    local url="http://${web_container_ip}:5555"
    if [ "${action}" = "headless" ]; then
        color_bold_green='\033[1;32m'
        color_off='\033[0m'
        echo -e "${color_bold_green}Open ${url} to see web interface${color_off}"

        exit 0
    fi
    python -m webbrowser -t "${url}"
}

main "$@"
