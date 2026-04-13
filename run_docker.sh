mount_data_dir=/Users/xuliang/ATLAS/MyHbbAnalysis/cache
mount_in_container=/root/analysis/cache
echo "Mount data dir ${mount_data_dir} to: ${mount_in_container}"


docker run -p 9009:9009 -it --rm \
  --add-host=host.docker.internal:host-gateway \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -v "$mount_data_dir":"${mount_in_container}" \
  --add-host=host.docker.internal:host-gateway \
  -e http_proxy=http://host.docker.internal:7890 \
  -e https_proxy=http://host.docker.internal:7890 \
  --entrypoint bash \
  hepex-purple-agent:local


   
#  --entrypoint bash \
#  -e ANTHROPIC_BASE_URL=$ANTHROPIC_BASE_URL \
#  -e ANTHROPIC_AUTH_TOKEN=$ANTHROPIC_AUTH_TOKEN \
#  -e DISABLE_AUTOUPDATER=1 \
#  -e NODE_TLS_REJECT_UNAUTHORIZED=0 \


