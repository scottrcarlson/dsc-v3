#!/bin/bash
sudo service ntp stop
sudo ntpd -gq
sudo service ntp start
sudo hwclock -w

