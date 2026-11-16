/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.vulkan;

import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import static org.junit.jupiter.api.Assertions.*;

/** Pins the narrow format/readback interception to the actual Minecraft binary. */
class HdrMixinTargetTest {
    @Test
    void mainTargetStoresItsFormatThroughTheSuperclassConstructor() throws Exception {
        MethodNode constructor = method("com/mojang/blaze3d/pipeline/MainTarget", "<init>", "(II)V");
        assertEquals(1, calls(constructor, "com/mojang/blaze3d/pipeline/RenderTarget", "<init>",
                "(Ljava/lang/String;Lcom/mojang/renderpearl/api/GpuFormat;Lcom/mojang/renderpearl/api/GpuFormat;)V"));
    }

    @Test
    void onePostChainDescriptorFeedsPersistentAndTransientTargets() throws Exception {
        MethodNode add = method("net/minecraft/client/renderer/PostChain", "addToFrame",
                "(Lcom/mojang/blaze3d/framegraph/FrameGraphBuilder;IILnet/minecraft/client/renderer/PostChain$TargetBundle;)V");
        assertEquals(1, calls(add, "com/mojang/blaze3d/resource/RenderTargetDescriptor$TextureProperties", "<init>",
                "(Lorg/joml/Vector4fc;Lcom/mojang/renderpearl/api/GpuFormat;)V"));
        assertEquals(1, calls(add, "net/minecraft/client/renderer/PostChain", "getOrCreatePersistentTarget", null));
        assertEquals(1, calls(add, "com/mojang/blaze3d/framegraph/FrameGraphBuilder", "createInternal", null));
    }

    @Test
    void screenshotSavingAndThumbnailOverloadStillShareTheReadbackEntryPoint() throws Exception {
        String target = "(Lcom/mojang/blaze3d/pipeline/RenderTarget;ILjava/util/function/Consumer;)V";
        method("net/minecraft/client/Screenshot", "takeScreenshot", target);
        MethodNode grab = method("net/minecraft/client/Screenshot", "grab",
                "(Ljava/io/File;Ljava/lang/String;Lcom/mojang/blaze3d/pipeline/RenderTarget;ILjava/util/function/Consumer;)V");
        assertEquals(1, calls(grab, "net/minecraft/client/Screenshot", "takeScreenshot", target));
        MethodNode thumbnail = method("net/minecraft/client/Screenshot", "takeScreenshot",
                "(Lcom/mojang/blaze3d/pipeline/RenderTarget;Ljava/util/function/Consumer;)V");
        assertEquals(1, calls(thumbnail, "net/minecraft/client/Screenshot", "takeScreenshot", target));
    }

    private static int calls(MethodNode method, String owner, String name, String descriptor) {
        int count = 0;
        for (var instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call && call.owner.equals(owner) && call.name.equals(name)
                    && (descriptor == null || call.desc.equals(descriptor))) count++;
        }
        return count;
    }

    private static MethodNode method(String owner, String name, String descriptor) throws Exception {
        try (InputStream source = HdrMixinTargetTest.class.getResourceAsStream("/" + owner + ".class")) {
            assertNotNull(source, owner);
            ClassNode node = new ClassNode();
            new ClassReader(source).accept(node, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
            return node.methods.stream().filter(method -> method.name.equals(name) && method.desc.equals(descriptor))
                    .findFirst().orElseThrow();
        }
    }
}
