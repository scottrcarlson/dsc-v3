#!/bin/bash
hg summary | grep parent > rev

scp *.py rev dsc@192.168.1.1:~/dsc2
scp *.py rev dsc@192.168.1.2:~/dsc2
scp *.py rev dsc@192.168.1.3:~/dsc2
scp *.py rev dsc@192.168.1.4:~/dsc2
scp *.py rev dsc@192.168.1.5:~/dsc2
scp *.py rev dsc@192.168.1.6:~/dsc2


