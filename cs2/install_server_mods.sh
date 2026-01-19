#!/usr/bin/env bash
CS2_ROOT=$HOME/games/game
METAMOD_RELEASE_URL="https://mms.alliedmods.net/mmsdrop/2.0/mmsource-2.0.0-git1284-linux.tar.gz "
CSSWR_RELEASE_URL="https://github.com/roflmuffin/CounterStrikeSharp/releases/download/v193/counterstrikesharp-with-runtime-build-193-linux-36a97bf.zip"

echo -e "Downloading and installing metamod. Latest releases here: https://www.sourcemm.net/downloads.php?branch=dev"
wget -q -O mm.tar.gz $METAMOD_RELEASE_URL
echo -e "Extracting metamod to csgo\n"
tar -zxvf mm.tar.gz -C $CS2_ROOT/csgo/ > /dev/null 2>&1

echo -e "Downloading and installing CounterStrikeSharp with Runtime. Latest releases here: https://github.com/roflmuffin/CounterStrikeSharp/releases"
wget -q -O csswr.zip $CSSWR_RELEASE_URL
unzip csswr.zip -d $CS2_ROOT/csgo/


echo "Ensure that ~/games/game/csgo/gameinfo.gi has the line"
echo -e "\tGame    csgo/addons/metamod"
echo "directly underneath"
echo -e "\tGame_LowViolence    csgo_lv"
echo "If this is set up correctly, the server command 'meta list' should work"

# https://github.com/NockyCZ/CS2-Deathmatch/releases
CS2_DM_MOD="https://github.com/NockyCZ/CS2-Deathmatch/releases/download/v1.0.9/Deathmatch.zip"
wget -q -O Deathmatch.zip $CS2_DM_MOD
unzip Deathmatch.zip -d $CS2_ROOT/

# https://github.com/ssypchenko/cs2-gungame/releases/tag/V1.0.8
# edit weapons here: $CS2_ROOT/csgo/cfg/gungame/gungame_weapons.json
# edit general options here: $CS2_ROOT/csgo/addons/counterstrikesharp/configs/plugins/GG2/GG2.json
CS2_GG_MOD="https://github.com/ssypchenko/cs2-gungame/releases/download/V1.0.8/GG2.plugin.1.0.8.zip"
#wget -q -O GG2.zip $CS2_GG_MOD
#unzip GG2.zip -d $CS2_ROOT/
