#!/bin/bash
docker stop pmm
docker rm pmm
docker run \
  --name=pmm \
  -v $PWD:/app \
  -v $PWD/config:/config \
  pmm -r --debug --trace --collections-only --run-collections "Captain America" 
