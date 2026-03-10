#!/bin/bash
# ============================================
# Download OpenVINO models for Theme Song Entrance System
# ============================================
set -e

MODELS_DIR="$(dirname "$0")/models"
BASE_URL="https://storage.openvinotoolkit.org/repositories/open_model_zoo/2023.0/models_bin/1"

mkdir -p "$MODELS_DIR"

echo "========================================"
echo "Downloading OpenVINO models..."
echo "========================================"

# Face Detection model (fast, retail quality)
echo ""
echo "[1/2] face-detection-retail-0005"
FACE_DET_URL="$BASE_URL/face-detection-retail-0005/FP16"
wget -nv -O "$MODELS_DIR/face-detection-retail-0005.xml" "$FACE_DET_URL/face-detection-retail-0005.xml" 2>&1
wget -nv -O "$MODELS_DIR/face-detection-retail-0005.bin" "$FACE_DET_URL/face-detection-retail-0005.bin" 2>&1
echo "   ✓ Downloaded"

# Face Re-identification model (generates 256-d embedding per face)
echo ""
echo "[2/2] face-reidentification-retail-0095"
FACE_REID_URL="$BASE_URL/face-reidentification-retail-0095/FP16"
wget -nv -O "$MODELS_DIR/face-reidentification-retail-0095.xml" "$FACE_REID_URL/face-reidentification-retail-0095.xml" 2>&1
wget -nv -O "$MODELS_DIR/face-reidentification-retail-0095.bin" "$FACE_REID_URL/face-reidentification-retail-0095.bin" 2>&1
echo "   ✓ Downloaded"

echo ""
echo "========================================"
echo "All models downloaded to: $MODELS_DIR"
echo "========================================"
ls -lh "$MODELS_DIR"
