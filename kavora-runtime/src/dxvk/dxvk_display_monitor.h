// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
#pragma once

#include <array>
#include <cstdint>
#include <memory>

namespace dxvk {

  struct DxvkDisplayMonitorInfo {
    uintptr_t monitor = 0;
    bool known = false;
    bool hdrEnabled = false;
    float paperWhiteNits = 200.0f;
    float peakNits = 0.0f;
    float minimumNits = 0.0f;
    std::array<float, 2> redPrimary {};
    std::array<float, 2> greenPrimary {};
    std::array<float, 2> bluePrimary {};
    std::array<float, 2> whitePoint {};
  };

  class DxvkDisplayMonitor {
  public:
    DxvkDisplayMonitor();
    ~DxvkDisplayMonitor();
    DxvkDisplayMonitorInfo query(void* window);

  private:
    struct Impl;
    std::unique_ptr<Impl> m_impl;
  };

}
