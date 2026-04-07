docker run -p 9009:9009 -it --rm \
  --add-host=host.docker.internal:host-gateway \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e http_proxy=http://host.docker.internal:7890 \
  -e https_proxy=http://host.docker.internal:7890 \
  hepex-purple-agent:local

#  --entrypoint bash \
#  -e ANTHROPIC_BASE_URL=$ANTHROPIC_BASE_URL \
#  -e ANTHROPIC_AUTH_TOKEN=$ANTHROPIC_AUTH_TOKEN \
#  -e DISABLE_AUTOUPDATER=1 \
#  -e NODE_TLS_REJECT_UNAUTHORIZED=0 \


