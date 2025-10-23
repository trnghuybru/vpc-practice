#!/bin/bash
set -e
cd /opt/quizapp
git pull --rebase
pip3 install -r requirements.txt
sudo systemctl restart quizapp