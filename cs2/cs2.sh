#!/usr/bin/env bash
cd $HOME/games/game/bin/linuxsteamrt64
HOSTED_WORKSHOP_COLLECTION_ID=3171582798

# dedicated launches a server
# usercon allows rcon
# high prioritises the process (possibly)
# ip 0.0.0.0 allows anyone to rcon. really this should be local subnet
# nomaster prevents showing up in global server browser
# threads 4 gives it four CPU threads. probs overkill
./cs2 \
    -dedicated \
    -usercon \
    -high \
    -ip 0.0.0.0 \
    -strictportbind \
    -nomaster \
    -threads 4 \
    -maxplayers 64 \
    +game_alias casual \
    +host_workshop_collection $HOSTED_WORKSHOP_COLLECTION_ID \
    +map de_dust2
