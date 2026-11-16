// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT

#include <algorithm>
#include <cwchar>
#include <vector>

#include <windows.h>
#include <dxgi1_6.h>

#include "dxvk_display_monitor.h"
#include "../util/com/com_pointer.h"

namespace dxvk {

  struct DxvkDisplayMonitor::Impl {
    HMODULE library = LoadLibraryExW(L"dxgi.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    HMONITOR monitor = nullptr;
    Com<IDXGIFactory1> factory;
    Com<IDXGIOutput6> output;
    LUID adapterId {};
    uint32_t targetId = 0;
    bool hasTarget = false;
    std::vector<DISPLAYCONFIG_PATH_INFO> paths;
    std::vector<DISPLAYCONFIG_MODE_INFO> modes;

    ~Impl() {
      output = nullptr;
      factory = nullptr;
      if (library != nullptr) {
        FreeLibrary(library);
      }
    }

    void findTarget(const wchar_t* deviceName) {
      hasTarget = false;
      UINT32 pathCount = 0;
      UINT32 modeCount = 0;
      // Display topology can change between sizing and enumeration.
      for (uint32_t attempt = 0; attempt < 2; ++attempt) {
        if (GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, &pathCount, &modeCount) != ERROR_SUCCESS) {
          return;
        }
        paths.resize(pathCount);
        modes.resize(modeCount);
        const LONG result = QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, &pathCount, paths.data(),
          &modeCount, modes.data(), nullptr);
        if (result == ERROR_INSUFFICIENT_BUFFER) {
          continue;
        }
        if (result != ERROR_SUCCESS) {
          return;
        }
        for (UINT32 i = 0; i < pathCount; ++i) {
          DISPLAYCONFIG_SOURCE_DEVICE_NAME source {};
          source.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME;
          source.header.size = sizeof(source);
          source.header.adapterId = paths[i].sourceInfo.adapterId;
          source.header.id = paths[i].sourceInfo.id;
          if (DisplayConfigGetDeviceInfo(&source.header) == ERROR_SUCCESS
              && std::wcscmp(source.viewGdiDeviceName, deviceName) == 0) {
            adapterId = paths[i].targetInfo.adapterId;
            targetId = paths[i].targetInfo.id;
            hasTarget = true;
            return;
          }
        }
        return;
      }
    }

    void refresh(HMONITOR current) {
      monitor = current;
      output = nullptr;
      factory = nullptr;
      hasTarget = false;
      if (library == nullptr || monitor == nullptr) {
        return;
      }
      using CreateFactory = HRESULT (WINAPI *)(REFIID, void**);
      const auto create = reinterpret_cast<CreateFactory>(GetProcAddress(library, "CreateDXGIFactory1"));
      if (create == nullptr || FAILED(create(__uuidof(IDXGIFactory1), reinterpret_cast<void**>(&factory)))) {
        return;
      }
      for (UINT a = 0; ; ++a) {
        Com<IDXGIAdapter1> adapter;
        if (factory->EnumAdapters1(a, &adapter) != S_OK) {
          break;
        }
        for (UINT o = 0; ; ++o) {
          Com<IDXGIOutput> candidate;
          if (adapter->EnumOutputs(o, &candidate) != S_OK) {
            break;
          }
          DXGI_OUTPUT_DESC desc {};
          if (SUCCEEDED(candidate->GetDesc(&desc)) && desc.Monitor == monitor) {
            candidate->QueryInterface(__uuidof(IDXGIOutput6), reinterpret_cast<void**>(&output));
            findTarget(desc.DeviceName);
            return;
          }
        }
      }
    }
  };

  DxvkDisplayMonitor::DxvkDisplayMonitor() : m_impl(std::make_unique<Impl>()) { }
  DxvkDisplayMonitor::~DxvkDisplayMonitor() = default;

  DxvkDisplayMonitorInfo DxvkDisplayMonitor::query(void* window) {
    DxvkDisplayMonitorInfo result;
    if (window == nullptr || !IsWindow(static_cast<HWND>(window))) {
      return result;
    }
    const auto current = MonitorFromWindow(static_cast<HWND>(window), MONITOR_DEFAULTTONEAREST);
    auto& state = *m_impl;
    if (current != state.monitor || state.factory == nullptr || !state.factory->IsCurrent()) {
      state.refresh(current);
    }
    result.monitor = reinterpret_cast<uintptr_t>(current);
    DXGI_OUTPUT_DESC1 desc {};
    if (state.output == nullptr || FAILED(state.output->GetDesc1(&desc))) {
      return result;
    }
    result.known = true;
    result.hdrEnabled = desc.ColorSpace == DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020;
    result.peakNits = desc.MaxLuminance;
    result.minimumNits = desc.MinLuminance;
    std::copy_n(desc.RedPrimary, 2, result.redPrimary.begin());
    std::copy_n(desc.GreenPrimary, 2, result.greenPrimary.begin());
    std::copy_n(desc.BluePrimary, 2, result.bluePrimary.begin());
    std::copy_n(desc.WhitePoint, 2, result.whitePoint.begin());
    if (state.hasTarget) {
      DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO color {};
      color.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO;
      color.header.size = sizeof(color);
      color.header.adapterId = state.adapterId;
      color.header.id = state.targetId;
      if (DisplayConfigGetDeviceInfo(&color.header) == ERROR_SUCCESS) {
        result.hdrEnabled = result.hdrEnabled && color.advancedColorEnabled;
      }
      DISPLAYCONFIG_SDR_WHITE_LEVEL white {};
      white.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SDR_WHITE_LEVEL;
      white.header.size = sizeof(white);
      white.header.adapterId = state.adapterId;
      white.header.id = state.targetId;
      if (DisplayConfigGetDeviceInfo(&white.header) == ERROR_SUCCESS && white.SDRWhiteLevel) {
        result.paperWhiteNits = float(white.SDRWhiteLevel) * 0.08f;
      }
    }
    return result;
  }

}
