from pathlib import Path
root=Path('无限画布/infinite-canvas/web/src')
p=root/'lib/canvas/workspace.ts';p.write_text('''export const isAPlusWorkspace = new URLSearchParams(window.location.search).get("workspace") === "a_plus";
export const canvasWorkspaceTitle = isAPlusWorkspace ? "A+画布" : "无限画布";
''',encoding='utf-8')
keys=['main_image_a_plus','a_plus_reference_lab','a_plus_style_model_replace','a_plus_first_screen_selling_points','amazon_to_walmart_a_plus','a_plus_hero_style_reverse','amazon_a_plus']
labels=['主图生A+','A+版式参考实验室','A+首屏风格复刻','首屏+卖点融合','亚马逊A+改沃尔玛A+','A+首屏风格反推','自由创作PSD']
p=root/'types/canvas.ts';s=p.read_text(encoding='utf-8');s=s.replace('    | "ai_qa_image";','    | "ai_qa_image"\n'+ '\n'.join('    | "'+k+'"' for k in keys)+';');p.write_text(s,encoding='utf-8')
p=root/'services/api/xiaoha.ts';s=p.read_text(encoding='utf-8');s='import { isAPlusWorkspace } from "@/lib/canvas/workspace";\n'+s
anchor='export const DEFAULT_XIAOHA_IMAGE_FEATURE:'
pos=s.index(anchor)
s=s[:pos]+'''export const A_PLUS_IMAGE_FEATURE_OPTIONS: XiaohaImageFeatureOption[] = [
'''+ '\n'.join('    { value: "'+k+'", label: "'+label+'", fixedEngine: true'+(', requiresReference: true' if k in ['a_plus_style_model_replace','a_plus_first_screen_selling_points'] else '')+' },' for k,label in zip(keys,labels))+'''
];
export const isAPlusFeature = (value: string) => A_PLUS_IMAGE_FEATURE_OPTIONS.some((item) => item.value === value);

'''+s[pos:]
s=s.replace('= "modelHd";\nexport const XIAOHA_IMAGE_FEATURE_OPTIONS', '= isAPlusWorkspace ? "main_image_a_plus" : "modelHd";\nexport const XIAOHA_IMAGE_FEATURE_OPTIONS',1)
s=s.replace('    { value: "product_retouch",','    ...A_PLUS_IMAGE_FEATURE_OPTIONS,\n    { value: "product_retouch",',1)
s=s.replace('export function getXiaohaImageFeatureOption', 'export const workspaceImageFeatureOptions = isAPlusWorkspace ? A_PLUS_IMAGE_FEATURE_OPTIONS : XIAOHA_IMAGE_FEATURE_OPTIONS;\n\nexport function getXiaohaImageFeatureOption')
s=s.replace('    image?: string;','    image?: string;\n    images?: string[];',1)
# Keep existing callers returning a single image; A+ caller retrieves all outputs.
anchor='export async function recordCanvasImageUsage'
pos=s.index(anchor)
s=s[:pos]+'''export async function requestXiaohaAPlusFeature(references: ReferenceImage[], feature: CanvasXiaohaImageFeature, prompt: string, signal?: AbortSignal) {
    const images = await Promise.all(references.map((reference) => imageToDataUrl({ dataUrl: reference.dataUrl, storageKey: reference.storageKey })));
    if (!images.length || images.some((image) => !image)) throw new Error("请连接可读取的A+素材图片");
    const response = await fetch(xiaohaApiUrl("image-feature"), {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ feature, images, prompt: prompt.trim() }), signal,
    });
    const payload = (await response.json().catch(() => ({}))) as ModelHdResponse;
    if (!response.ok || !payload.success || !payload.images?.length) throw new Error(payload.message || `A+处理失败（HTTP ${response.status}）`);
    return payload.images;
}

'''+s[pos:];p.write_text(s,encoding='utf-8')
p=root/'stores/canvas/use-canvas-store.ts';s=p.read_text(encoding='utf-8');s='import { isAPlusWorkspace } from "@/lib/canvas/workspace";\n'+s;s=s.replace('const CANVAS_STORE_KEY = "infinite-canvas:canvas_store";', 'const CANVAS_STORE_KEY = isAPlusWorkspace ? "infinite-canvas:a_plus_canvas_store" : "infinite-canvas:canvas_store";');p.write_text(s,encoding='utf-8')
p=root/'pages/canvas/index.tsx';s=p.read_text(encoding='utf-8');s='import { canvasWorkspaceTitle } from "@/lib/canvas/workspace";\n'+s;s=s.replace('`无限画布 ${projects.length + 1}`','`${canvasWorkspaceTitle} ${projects.length + 1}`');s=s.replace('font-semibold">无限画布</h1>','font-semibold">{canvasWorkspaceTitle}</h1>');p.write_text(s,encoding='utf-8')
p=root/'components/canvas/canvas-node-prompt-panel.tsx';s=p.read_text(encoding='utf-8').replace('    XIAOHA_IMAGE_FEATURE_OPTIONS,','    workspaceImageFeatureOptions,\n    isAPlusFeature,');s=s.replace('options={XIAOHA_IMAGE_FEATURE_OPTIONS.map','options={workspaceImageFeatureOptions.map')
s=s.replace('    const hasRequiredReference =', '    const hasInputImage = hasImageContent || (isAPlusFeature(imageFeature) && connectedImageCount > 0);\n    const hasRequiredReference =')
s=s.replace('const hasRequiredReference = !imageFeatureOption.requiresReference || connectedImageCount > 0;', 'const hasRequiredReference = !imageFeatureOption.requiresReference || connectedImageCount >= (hasImageContent ? 1 : 2);')
s=s.replace('!hasImageContent || !hasRequiredReference','!hasInputImage || !hasRequiredReference').replace('? hasImageContent && hasRequiredReference','? hasInputImage && hasRequiredReference')
p.write_text(s,encoding='utf-8')
p=root/'pages/canvas/project.tsx';s=p.read_text(encoding='utf-8');s=s.replace('    DEFAULT_MODEL_HD_METHOD,','    DEFAULT_MODEL_HD_METHOD,\n    isAPlusFeature,\n    requestXiaohaAPlusFeature,',1)
s=s.replace('                  : [];\n            if (!isXiaohaImageRequest', '                  : isAPlusFeature(imageFeature) ? connectedSourceImages : [];\n            if (!isXiaohaImageRequest',1)
anchor='    const deleteNodes = useCallback('
assert s.count(anchor)==1
s=s.replace(anchor,'''    const createAPlusModule = useCallback((feature: import("@/types/canvas").CanvasXiaohaImageFeature) => {
        const sources = nodesRef.current.filter((node) => selectedNodeIdsRef.current.has(node.id) && node.type === CanvasNodeType.Image && node.metadata?.content);
        const node = createCanvasNode(CanvasNodeType.Image, getCanvasCenter(), { imageFunction: feature, status: NODE_STATUS_IDLE, prompt: "" });
        node.title = getXiaohaImageFeatureOption(feature).label;
        setNodes((prev) => [...prev, node]);
        setConnections((prev) => [...prev, ...sources.map((source) => ({ id: nanoid(), fromNodeId: source.id, toNodeId: node.id }))]);
        setSelectedNodeIds(new Set([node.id]));
        setSelectedConnectionId(null);
        setDialogNodeId(node.id);
    }, [getCanvasCenter]);

'''+anchor)
s=s.replace('                    onAddModelHd={createModelHdModule}', '                    onAddModelHd={createModelHdModule}\n                    onAddAPlus={createAPlusModule}')
# A+ multi outputs get their own connected nodes, normal feature behavior remains unchanged.
s=s.replace('                        const image = await requestXiaohaImageFeature(', '                        const outputImages = isAPlusFeature(imageFeature)\n                            ? await requestXiaohaAPlusFeature(xiaohaSourceImages, imageFeature, featurePrompt, controller.signal)\n                            : [await requestXiaohaImageFeature(',1)
s=s.replace('                            outpaintSettings,\n                        );\n                        const uploaded = await uploadImage(image);', '                            outpaintSettings,\n                        )];\n                        const uploaded = await uploadImage(outputImages[0]);',1)
anchor='                        message.success(`${actionLabel}处理完成`);'
s=s.replace(anchor,'''                        for (const [index, image] of outputImages.slice(1).entries()) {
                            const extra = await uploadImage(image);
                            const size = fitNodeSize(extra.width, extra.height, imageConfig.width, imageConfig.height);
                            const extraId = nanoid();
                            setNodes((prev) => [...prev, { id: extraId, type: CanvasNodeType.Image,
                                title: `${actionLabel} · 第${index + 2}张`,
                                position: { x: parentPosition.x + (sourceNode?.width || imageConfig.width) + 96, y: parentPosition.y + (index + 1) * (imageConfig.height + 80) },
                                width: size.width, height: size.height, metadata: { ...imageMetadata(extra), imageFunction: imageFeature, sourceTitle } }]);
                            setConnections((prev) => [...prev, { id: nanoid(), fromNodeId: nodeId, toNodeId: extraId }]);
                        }
'''+anchor,1)
p.write_text(s,encoding='utf-8')
p=root/'components/canvas/canvas-toolbar.tsx';s=p.read_text(encoding='utf-8');s='import { A_PLUS_IMAGE_FEATURE_OPTIONS } from "@/services/api/xiaoha";\nimport type { CanvasXiaohaImageFeature } from "@/types/canvas";\nimport { isAPlusWorkspace } from "@/lib/canvas/workspace";\n'+s
s=s.replace('    onAddModelHd,','    onAddModelHd,\n    onAddAPlus,',1).replace('    onAddModelHd: () => void;','    onAddModelHd: () => void;\n    onAddAPlus: (feature: CanvasXiaohaImageFeature) => void;',1)
anchor='                    <button\n                        type="button"\n                        className="flex w-full cursor-pointer items-start gap-3'
assert s.count(anchor)==1
s=s.replace(anchor,'''                    {A_PLUS_IMAGE_FEATURE_OPTIONS.map((option) => (
                        <button key={option.value} type="button" className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-left text-sm"
                            style={{ color: theme.toolbar.activeText }} onClick={() => { onAddAPlus(option.value); setModulesOpen(false); }}>
                            <Sparkles className="size-4" />{option.label}
                        </button>
                    ))}
                    {!isAPlusWorkspace ? <button
                        type="button"
                        className="flex w-full cursor-pointer items-start gap-3''')
s=s.replace('                    </button>\n                </div>\n            ) : null}\n\n            {appearanceOpen', '                    </button> : null}\n                </div>\n            ) : null}\n\n            {appearanceOpen',1)
p.write_text(s,encoding='utf-8')
