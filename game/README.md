# Welcome to Evennia!

This is your game directory, set up to let you start with
your new game right away. An overview of this directory is found here:
https://github.com/evennia/evennia/wiki/Directory-Overview#the-game-directory

You can delete this readme file when you've read it and you can
re-arrange things in this game-directory to suit your own sense of
organisation (the only exception is the directory structure of the
`server/` directory, which Evennia expects). If you change the structure
you must however also edit/add to your settings file to tell Evennia
where to look for things.

Your game's main configuration file is found in
`server/conf/settings.py` (but you don't need to change it to get
started). If you just created this directory (which means you'll already
have a `virtualenv` running if you followed the default instructions),
`cd` to this directory then initialize a new database using

    evennia migrate

To start the server, stand in this directory and run

    evennia start

프로젝트의 빠른 실행은 [루트 README](../README.md#빠른-시작), 설치·서버 운영은 [설치 안내](../docs/installation.md)를 따른다.
기본 Telnet은 TCP 8700, 게임 Web 화면은 `http://localhost:8701/webclient/`다.
접속 서비스는 모든 IPv4 인터페이스에 bind하므로 LAN 접근과 키 관리 정책도 해당 안내를 확인한다.

# Getting started

From here on you might want to look at one of the beginner tutorials:
http://github.com/evennia/evennia/wiki/Tutorials.

Evennia's documentation is here:
https://github.com/evennia/evennia/wiki.

Enjoy!
