#!/bin/bash
docker build -t pmm .
docker stop pmm
docker rm pmm
