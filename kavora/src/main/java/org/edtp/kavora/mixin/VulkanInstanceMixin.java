/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import com.mojang.renderpearl.backend.vulkan.VulkanInstance;
import java.nio.ByteBuffer;
import org.edtp.kavora.NativeRuntime;
import org.lwjgl.PointerBuffer;
import org.lwjgl.system.MemoryStack;
import org.lwjgl.vulkan.VkAllocationCallbacks;
import org.lwjgl.vulkan.VkInstance;
import org.lwjgl.vulkan.VkInstanceCreateInfo;
import org.lwjgl.vulkan.VkExtensionProperties;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

@Mixin(value = VulkanInstance.class, remap = false)
public abstract class VulkanInstanceMixin {
    @ModifyArg(method = "<init>", at = @At(value = "INVOKE",
            target = "Lorg/lwjgl/vulkan/VkApplicationInfo;apiVersion(I)Lorg/lwjgl/vulkan/VkApplicationInfo;"))
    private int kavora$instanceVersion(int version) {
        return org.lwjgl.vulkan.VK14.VK_API_VERSION_1_4;
    }

    @WrapOperation(method = "<init>", at = @At(value = "INVOKE",
            target = "Lorg/lwjgl/vulkan/VK12;vkCreateInstance(Lorg/lwjgl/vulkan/VkInstanceCreateInfo;Lorg/lwjgl/vulkan/VkAllocationCallbacks;Lorg/lwjgl/PointerBuffer;)I"))
    private int kavora$prepareRuntime(VkInstanceCreateInfo info, VkAllocationCallbacks allocator,
                                      PointerBuffer output, Operation<Integer> original) {
        NativeRuntime.prepareVulkan();
        // Keep the extension names on the constructor's stack until its LWJGL dispatch table has read them.
        MemoryStack stack = MemoryStack.stackGet();
        String[] additions = {
                org.lwjgl.vulkan.KHRGetSurfaceCapabilities2.VK_KHR_GET_SURFACE_CAPABILITIES_2_EXTENSION_NAME,
                // NRC resolves the KHR entry points even when their core equivalents are available.
                org.lwjgl.vulkan.KHRGetPhysicalDeviceProperties2.VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME,
                org.lwjgl.vulkan.EXTSwapchainColorspace.VK_EXT_SWAPCHAIN_COLOR_SPACE_EXTENSION_NAME
        };
        PointerBuffer requested = info.ppEnabledExtensionNames();
        PointerBuffer extensions = stack.mallocPointer(info.enabledExtensionCount() + additions.length);
        for (int i = 0; i < info.enabledExtensionCount(); i++) extensions.put(requested.get(i));
        for (String name : additions) {
            boolean present = false;
            for (int i = 0; i < info.enabledExtensionCount(); i++) present |= name.equals(requested.getStringUTF8(i));
            boolean optional = name.equals(org.lwjgl.vulkan.EXTSwapchainColorspace.VK_EXT_SWAPCHAIN_COLOR_SPACE_EXTENSION_NAME);
            if (!present && (!optional || kavora$instanceExtensionAvailable(name, stack))) extensions.put(stack.UTF8(name));
        }
        info.ppEnabledExtensionNames(extensions.flip());
        int result = original.call(info, allocator, output);
        if (result == org.lwjgl.vulkan.VK10.VK_SUCCESS) NativeRuntime.recordInstance(output.get(0), info);
        return result;
    }

    private static boolean kavora$instanceExtensionAvailable(String name, MemoryStack stack) {
        var count = stack.mallocInt(1);
        if (org.lwjgl.vulkan.VK10.vkEnumerateInstanceExtensionProperties((ByteBuffer) null, count, null)
                != org.lwjgl.vulkan.VK10.VK_SUCCESS || count.get(0) == 0) return false;
        var properties = VkExtensionProperties.calloc(count.get(0), stack);
        if (org.lwjgl.vulkan.VK10.vkEnumerateInstanceExtensionProperties((ByteBuffer) null, count, properties)
                != org.lwjgl.vulkan.VK10.VK_SUCCESS) return false;
        for (int i = 0; i < count.get(0); i++) {
            if (name.equals(properties.get(i).extensionNameString())) return true;
        }
        return false;
    }

    @WrapOperation(method = "close", at = @At(value = "INVOKE",
            target = "Lorg/lwjgl/vulkan/VK12;vkDestroyInstance(Lorg/lwjgl/vulkan/VkInstance;Lorg/lwjgl/vulkan/VkAllocationCallbacks;)V"))
    private void kavora$closeRuntime(VkInstance instance, VkAllocationCallbacks allocator, Operation<Void> original) {
        NativeRuntime.beforeInstanceDestroy(instance.address());
        original.call(instance, allocator);
    }
}
