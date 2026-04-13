wait_for_port() {
local timeout=30
    local elapsed=0
    printf "Scanning 127.0.0.1:9009 "

    while [ $elapsed -lt $timeout ]; do
        if curl -s --noproxy "*" http://127.0.0.1:9009 > /dev/null 2>&1; then
            echo "\n[Success] Agent is reachable in $elapsed seconds! (^_−)☆"
            return 0
        fi

        printf "."

        sleep 1
        ((elapsed++))
    done

    echo "\n[Error] Still can't reach Agent in ${timeout}s."
    echo "Diagnostic: Check if 'docker ps' shows the container as UP."
    docker ps | grep hepex-purple-agent
    exit 1
}

build_and_run_purple_agnet() {
    echo "Building purple agent..."
    docker build -t hepex-purple-agent:local .

    echo "(Re)Starting purple agent container..."

    mount_data_dir=/Users/xuliang/ATLAS/MyHbbAnalysis/cache
    mount_in_container=/home/agent/analysis/cache
    echo "Mount data dir ${mount_data_dir} to: ${mount_in_container}"
    docker rm -f hepex-purple-agent
    docker run -p 9009:9009 \
      -d --name hepex-purple-agent \
      -v "$mount_data_dir":"${mount_in_container}" \
      --add-host=host.docker.internal:host-gateway \
      -e OPENAI_API_KEY=$OPENAI_API_KEY \
      -e http_proxy=http://host.docker.internal:7890 \
      -e https_proxy=http://host.docker.internal:7890 \
      hepex-purple-agent:local

    echo "Purple agent container started."
#      -e ANTHROPIC_AUTH_TOKEN=$ANTHROPIC_AUTH_TOKEN \
#      -e ANTHROPIC_BASE_URL=$ANTHROPIC_BASE_URL \
#      -e DISABLE_AUTOUPDATER=1 \
#      -e NODE_TLS_REJECT_UNAUTHORIZED=0 \
#
}

build_and_run_purple_agnet

wait_for_port 9009 30

uv run pytest tests/test_e2e_green_white_hbb.py -v -s
