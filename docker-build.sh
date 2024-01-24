#!/bin/bash
VERSION=$(cat $PWD/VERSION)
if [[ -z $VERSION ]]; then
    echo "Unable to read version - exiting."
    exit
else
    echo "Building Emby-Meta-Manager:$VERSION"
    docker build -t emby-meta-manager:$VERSION .
fi