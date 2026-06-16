
# Format: "FILENAME,optional human comment"
# 2456 is the background for the menus and should be kept, but single color will make it just 3% of the size!
# 0966 is a poster, replace it by something smaller?
# 0095 is the night sky with stars
# 0089-0093 are the skyline, replace with something smaller? or something repeating?
# WIND54.VOC is also playing at the start of the game but not that interesting
# cool: FIRE09.VOC,38k
EXCLUDE_CSVS=$(cat <<'EOF'
TILE1102.PNG,some high def image
TILE2445.PNG,help screen can be omitted in this pack
TILE2456.PNG,menu background is very big and will be replaced
TILE3260.PNG,end animation
TILE3263.PNG,end animation
TILE3264.PNG,end animation
TILE3265.PNG,end animation
TILE3266.PNG,end animation
TILE3267.PNG,end animation
TILE3268.PNG,end animation
TILE3270.PNG,how to order
TILE3271.PNG,mousepad and strategy guide
TILE3272.PNG,how to buy
TILE3273.PNG,3drealms promo
TILE3280.PNG,end story text
TILE3290.PNG,spaceship picture1
TILE3291.PNG,spaceship picture2
TILE3292.PNG,end story picture and text
GRABBAG.VOC,300k title song that is also included as midi
BONUS.VOC,274k
BARMUSIC.VOC,70k
!PRISON.VOC,
CHEW05.VOC,
!PIG.VOC
AMB81B.VOC,50k
!BOSS.VOC
WIND54.VOC
WARAMB23.VOC
WARAMB13.VOC
DSCREM38.VOC,unused
PAIN13.VOC,unused
PAIN28.VOC,unused
PIGWRN.VOC,unused
PISSIN01.VOC,unused
EOF
)

EXCLUDE_ARGS=()
while IFS= read -r csv; do
    [ -z "$csv" ] && continue
    filename=$(printf '%s' "$csv" | cut -d',' -f1 | tr -d '[:space:]')
    [ -z "$filename" ] && continue
    EXCLUDE_ARGS+=("--excludefiles" "$filename")
done <<EOF
$EXCLUDE_CSVS
EOF

# Only needed when using --maxsoundsize and still wanting these must haves:
# from full 1.3:
#flyby.voc,35K flying by shotgun shooters
# DIESOB03.WAV,15K die you son of a bitch - only used when boss is killed
# rarely used:
#HAIL01.WAV,19K hail to the king baby - random taunt
#LETGOD01.WAV,let god sort 'em out - random taunt
# sizes below are uncompressed VOC size:
INCLUDE_CSVS=$(cat <<'EOF'
SHOTGUN7.WAV,52KB shotgun sound is important for gameplay
PAY02.WAV,32k leave it because it's the intro "Damn those aliens are gonna pay for shooting up my ride"
BOMBEXPL.WAV,20K bomb explosion used for spaceship crash, exploding bottles
AHMUCH03.WAV,20K much better peeing sound
WAITIN03.WAV,16K what are you waiting for christmas - when inactive
NEEDED03.WAV,ah I needed that - when low health becomes higher
GASPS07.WAV,duke in pain - 16215
MICE3.WAV,14K crawling mice - not really needed?
FIRE09.WAV,9K beginning and helps for feeling hot
h2ogrgl2.wav,23K fire hydrant and broken toilet
EOF
)

INCLUDE_ARGS=()
while IFS= read -r csv; do
    echo "$csv"
    [ -z "$csv" ] && continue
    filename=$(printf '%s' "$csv" | cut -d',' -f1 | tr -d '[:space:]')
    echo "$filename"
    [ -z "$filename" ] && continue
    INCLUDE_ARGS+=("--includefiles" "$filename")
    echo "$INCLUDE_ARGS"
    echo "${INCLUDE_ARGS[@]}"
done <<EOF
$INCLUDE_CSVS
EOF

INCLUDE_CSVS_TINY=$(cat <<'EOF'
SHOTGUN7.WAV,52KB shotgun sound is important for gameplay
PAY02.WAV,32k leave it because it's the intro "Damn those aliens are gonna pay for shooting up my ride"
BOMBEXPL.WAV,20K bomb explosion used for spaceship crash, exploding bottles
EOF
)

INCLUDE_ARGS_TINY=()
while IFS= read -r csv; do
    echo "$csv"
    [ -z "$csv" ] && continue
    filename=$(printf '%s' "$csv" | cut -d',' -f1 | tr -d '[:space:]')
    echo "$filename"
    [ -z "$filename" ] && continue
    INCLUDE_ARGS_TINY+=("--includefiles" "$filename")
    echo "$INCLUDE_ARGS_TINY"
    echo "${INCLUDE_ARGS_TINY[@]}"
done <<EOF
$INCLUDE_CSVS_TINY
EOF

#   Source path supports spaces but NOT commas (comma is the field separator).
#   Paths are resolved relative to the script working directory.
#   Multiple tiles referencing the same source file are automatically
#   deduplicated in the GRP using tilefromtexture in duke3d.def.
#TILE3281.PNG,overrides/TILE0095.PNG,loading screen: atomic logo HQ
REPLACE_CSVS=$(cat <<'EOF'
TILE0089.PNG,overrides/TILE0095.PNG,sky
TILE0090.PNG,overrides/TILE0095.PNG,sky
TILE0091.PNG,overrides/TILE0095.PNG,sky
TILE0092.PNG,overrides/TILE0095.PNG,sky
TILE0093.PNG,overrides/TILE0095.PNG,sky
TILE0095.PNG,overrides/TILE0095.PNG,sky
TILE2456.PNG,overrides/TILE1141.PNG,menu background
EOF
)

REPLACE_ARGS=()
while IFS= read -r csv; do
    [ -z "$csv" ] && continue
    grp_name=$(printf '%s' "$csv" | cut -d',' -f1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    source_path=$(printf '%s' "$csv" | cut -d',' -f2 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [ -z "$grp_name" ] || [ -z "$source_path" ] && continue
    REPLACE_ARGS+=("--replacefile" "$grp_name" "$source_path")
done <<EOF
$REPLACE_CSVS
EOF

INPUT=input/DUKE3D_v1.3d_shareware.grp

OUTPUT_DIR="outputs"
mkdir -p "$OUTPUT_DIR"

# THESE precalculated_pngs* folders are created by first running it with --keep-temp and then renaming temp_folder to precalculated_pngs_...
# You can use ./longrun.sh for that


#PNGS=precalculated_pngs_full_1.3D/
PNGS=precalculated_pngs_shareware_1.3D/

#PNGQUANTS=precalculated_pngs_pngquant/
#PNGQUANTS=precalculated_pngs_pngquant_69-71_2/
#PNGQUANTS=precalculated_pngs_pngquant_40-71_2/
#PNGQUANTS=precalculated_pngs_full_1.3D_pngquant_40-71_2
PNGQUANTS=precalculated_pngs_pngquant_40-71_2_iterations_500


# 4 levels, heavy compromise:
#python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS" "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS[@]}" "${REPLACE_ARGS[@]}" --map E1L1.MAP,E1L2.MAP,E1L3.MAP,E1L4.MAP "$INPUT" --adpcmwidth 2 --maxsoundsize 15000 --output "$OUTPUT_DIR/E1L1-4_compromise.grp"
#zip -j -9 "$OUTPUT_DIR/E1L1-4_compromise.grp.zip" "$OUTPUT_DIR/E1L1-4_compromise.grp"
#exit 1


# 2 levels with compromise:
#python3 duke3d_compact_grp.py --camerasdestructable --keep-temp --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS" "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS[@]}" "${REPLACE_ARGS[@]}" --map E1L1.MAP,E1L2.MAP "$INPUT" --adpcmwidth 2 --maxsoundsize 15000 --output "$OUTPUT_DIR/E1L1-2_compromise.grp"
#zip -j -9 "$OUTPUT_DIR/E1L1-2_compromise.grp.zip" "$OUTPUT_DIR/E1L1-2_compromise.grp"
#exit


# 2 levels with compromise but based on the full to test:
# somehow this results in 200KB extra being added :-/
#python3 duke3d_compact_grp.py --camerasdestructable --zopflipng --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS" "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS[@]}" --map E1L1.MAP,E1L2.MAP input/DUKE3D_v1.3d_full.grp --adpcmwidth 2 --maxsoundsize 15000 --output "$OUTPUT_DIR/E1L1-2_compromise_from_full.grp"
#zip -j -9 "$OUTPUT_DIR/E1L1-2_compromise_from_full.grp.zip" "$OUTPUT_DIR/E1L1-2_compromise_from_full.grp"
#exit

PNGQUANTS_AGRESSIVE=precalculated_pngs_pngquant_10_3/

# All levels, complete but compressed audio and images:
# See the end

# All levels, nearly complete:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGS" "${EXCLUDE_ARGS[@]}" "$INPUT" --adpcmwidth 2 --output "$OUTPUT_DIR/E1L1-6_nearcomplete.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-6_nearcomplete.grp.zip" "$OUTPUT_DIR/E1L1-6_nearcomplete.grp"

# Some compromise:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS" "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS[@]}" "${REPLACE_ARGS[@]}" "$INPUT" --maxsoundsize 15000 --adpcmwidth 2 --output "$OUTPUT_DIR/E1L1-6_compromise.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-6_compromise.grp.zip" "$OUTPUT_DIR/E1L1-6_compromise.grp"

# All levels but tiny:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS_AGRESSIVE" "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS_TINY[@]}" "${REPLACE_ARGS[@]}" "$INPUT" --adpcmwidth 2 --maxsoundsize 5000 --nomenusongs --output "$OUTPUT_DIR/E1L1-6_tiny.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-6_tiny.grp.zip" "$OUTPUT_DIR/E1L1-6_tiny.grp"


# 4 levels, compromise:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS" "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS[@]}" "${REPLACE_ARGS[@]}" --map E1L1.MAP,E1L2.MAP,E1L3.MAP,E1L4.MAP "$INPUT" --adpcmwidth 2 --maxsoundsize 15000 --output "$OUTPUT_DIR/E1L1-4_compromise.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-4_compromise.grp.zip" "$OUTPUT_DIR/E1L1-4_compromise.grp"

# 4 levels, heavy compromise:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS" "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS[@]}" "${REPLACE_ARGS[@]}" --map E1L1.MAP,E1L2.MAP,E1L3.MAP,E1L4.MAP "$INPUT" --adpcmwidth 2 --maxsoundsize 12500 --output "$OUTPUT_DIR/E1L1-4_heavycompromise.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-4_heavycompromise.grp.zip" "$OUTPUT_DIR/E1L1-4_heavycompromise.grp"



# 3 levels, near complete:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGS" "${EXCLUDE_ARGS[@]}" --map E1L1.MAP,E1L2.MAP,E1L3.MAP "$INPUT" --adpcmwidth 2 --output "$OUTPUT_DIR/E1L1-3_nearcomplete.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-3_nearcomplete.grp.zip" "$OUTPUT_DIR/E1L1-3_nearcomplete.grp"

# 3 levels, compromise:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS" "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS[@]}" "${REPLACE_ARGS[@]}" --map E1L1.MAP,E1L2.MAP,E1L3.MAP "$INPUT" --adpcmwidth 2 --maxsoundsize 15000 --output "$OUTPUT_DIR/E1L1-3_compromise.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-3_compromise.grp.zip" "$OUTPUT_DIR/E1L1-3_compromise.grp"



# 2 levels but complete, just compressed:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGS" --map E1L1.MAP,E1L2.MAP "$INPUT" --adpcmwidth 2 --output "$OUTPUT_DIR/E1L1-2.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-2.grp.zip" "$OUTPUT_DIR/E1L1-2.grp"

# 2 levels, near complete:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGS" "${EXCLUDE_ARGS[@]}" --map E1L1.MAP,E1L2.MAP "$INPUT" --adpcmwidth 2 --output "$OUTPUT_DIR/E1L1-2_nearcomplete.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-2_nearcomplete.grp.zip" "$OUTPUT_DIR/E1L1-2_nearcomplete.grp"

# 2 levels with compromise:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS" "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS[@]}" "${REPLACE_ARGS[@]}" --map E1L1.MAP,E1L2.MAP "$INPUT" --adpcmwidth 2 --maxsoundsize 15000 --output "$OUTPUT_DIR/E1L1-2_compromise.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-2_compromise.grp.zip" "$OUTPUT_DIR/E1L1-2_compromise.grp"



# One level but complete, just compressed:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGS" --map E1L1.MAP "$INPUT" --adpcmwidth 2 --output "$OUTPUT_DIR/E1L1.grp"
zip -j -9 "$OUTPUT_DIR/E1L1.grp.zip" "$OUTPUT_DIR/E1L1.grp"

# One level but some compromise:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS" --map E1L1.MAP "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS[@]}" "${REPLACE_ARGS[@]}" "$INPUT" --adpcmwidth 2 --maxsoundsize 15000 --output "$OUTPUT_DIR/E1L1_compromise.grp"
zip -j -9 "$OUTPUT_DIR/E1L1_compromise.grp.zip" "$OUTPUT_DIR/E1L1_compromise.grp"

# One level, tiny:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS_AGRESSIVE" --map E1L1.MAP "${EXCLUDE_ARGS[@]}" "${INCLUDE_ARGS_TINY[@]}" "${REPLACE_ARGS[@]}" "$INPUT" --adpcmwidth 2 --maxsoundsize 5000 --nomenusongs --output "$OUTPUT_DIR/E1L1_tiny.grp"
zip -j -9 "$OUTPUT_DIR/E1L1_tiny.grp.zip" "$OUTPUT_DIR/E1L1_tiny.grp"

# Current minimal, no sounds, just to establish lower bound:
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGQUANTS_AGRESSIVE" --map E1L1.MAP "${EXCLUDE_ARGS[@]}" "${REPLACE_ARGS[@]}" "$INPUT" --adpcmwidth 2 --maxsoundsize 0 --nomenusongs --output "$OUTPUT_DIR/E1L1_minimal.grp"
zip -j -9 "$OUTPUT_DIR/E1L1_minimal.grp.zip" "$OUTPUT_DIR/E1L1_minimal.grp"


# All levels, everything included, compressed:
# Do this one last and --keep-temp for analysis
python3 duke3d_compact_grp.py --camerasdestructable --onlysmaller --adpcmwav --ultraminimalmenu --pngfolder "$PNGS" --keep-temp "$INPUT" --adpcmwidth 2 --output "$OUTPUT_DIR/E1L1-6.grp"
zip -j -9 "$OUTPUT_DIR/E1L1-6.grp.zip" "$OUTPUT_DIR/E1L1-6.grp"


