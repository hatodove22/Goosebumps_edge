#ifndef MODEL_LBP_LR_H
#define MODEL_LBP_LR_H

// -----------------------------------------------------------------------------
// Placeholder model header.
//
// Replace this file with an auto-generated header produced by:
//   python tools/export_lbp_lr_header.py --model models/lbp_lr_model.json \
//       --out firmware/<your_firmware>/include/model_lbp_lr.h
//
// The generated file will define:
//   - LBP_LR_BINS (256)
//   - LBP_LR_BIAS
//   - LBP_LR_THRESHOLD
//   - LBP_LR_WEIGHTS[256]
// -----------------------------------------------------------------------------

#define LBP_LR_BINS 256
static const float LBP_LR_BIAS = 0.0f;
static const float LBP_LR_THRESHOLD = 0.5f;
static const float LBP_LR_WEIGHTS[LBP_LR_BINS] = {0.0f};

#endif // MODEL_LBP_LR_H
