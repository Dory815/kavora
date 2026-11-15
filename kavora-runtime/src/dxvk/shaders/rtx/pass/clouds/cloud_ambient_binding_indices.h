// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
#pragma once

#include "rtx/pass/common_binding_indices.h"

#define CLOUD_AMBIENT_BINDING_PROBE 40
#define CLOUD_AMBIENT_BINDING_SAMPLER 41
#define CLOUD_AMBIENT_BINDING_OUTPUT 42

#if CLOUD_AMBIENT_BINDING_PROBE <= COMMON_MAX_BINDING
#error "Cloud ambient bindings overlap common bindings."
#endif
