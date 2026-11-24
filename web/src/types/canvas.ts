export type Position = {
    x: number;
    y: number;
};

export type ViewportTransform = {
    x: number;
    y: number;
    k: number;
};

export enum CanvasNodeType {
    Image = "image",
    Text = "text",
    Config = "config",
    Video = "video",
    Audio = "audio",
    Group = "group",
}

export type CanvasNodeStatus = "idle" | "success" | "loading" | "error";
export type CanvasGenerationMode = "text" | "image" | "video" | "audio";
export type CanvasImageGenerationType = "generation" | "edit";
export type CanvasBusinessModule = "modelHd";
export type CanvasXiaohaImageFeature =
    | "modelHd"
    | "product_retouch"
    | "product_retouch_local"
    | "background_cutout"
    | "jimeng_hd_upscale"
    | "remove_eyelashes"
    | "pose_change"
    | "scene_change"
    | "outpaint"
    | "single_to_double"
    | "skin_tone"
    | "pupil_color_change"
    | "eye_shape_change"
    | "three_view"
    | "ai_qa_image"
    | "main_image_a_plus"
    | "a_plus_reference_lab"
    | "a_plus_style_model_replace"
    | "a_plus_first_screen_selling_points"
    | "amazon_to_walmart_a_plus"
    | "a_plus_hero_style_reverse"
    | "amazon_a_plus"
    | "reference_reverse"
    | "reference_compose";
export type CanvasImageFunction = "generate" | CanvasXiaohaImageFeature;
export type CanvasModelHdMethod = "nano-banana-2" | "seedream-5-pro";

export type CanvasNodeMetadata = {
    referenceAnalysis?: Record<string, string>;
    referenceFields?: string[];
    referenceSourceNodeId?: string;
    psdFile?: { storageKey: string };
    content?: string;
    composerContent?: string;
    prompt?: string;
    status?: CanvasNodeStatus;
    errorDetails?: string;
    fontSize?: number;
    generationMode?: CanvasGenerationMode;
    generationType?: CanvasImageGenerationType;
    businessModule?: CanvasBusinessModule;
    imageFunction?: CanvasImageFunction;
    sourceTitle?: string;
    modelHdMethod?: CanvasModelHdMethod;
    outpaintTop?: number;
    outpaintBottom?: number;
    outpaintLeft?: number;
    outpaintRight?: number;
    model?: string;
    size?: string;
    quality?: string;
    count?: number;
    seconds?: string;
    vquality?: string;
    generateAudio?: string;
    watermark?: string;
    audioVoice?: string;
    audioFormat?: string;
    audioSpeed?: string;
    audioInstructions?: string;
    references?: string[];
    naturalWidth?: number;
    naturalHeight?: number;
    freeResize?: boolean;
    isBatchRoot?: boolean;
    batchRootId?: string;
    batchChildIds?: string[];
    batchUsesReferenceImages?: boolean;
    primaryImageId?: string;
    imageBatchExpanded?: boolean;
    storageKey?: string;
    mimeType?: string;
    bytes?: number;
    durationMs?: number;
    groupId?: string;
};

export type CanvasNodeData = {
    id: string;
    type: CanvasNodeType;
    title: string;
    position: Position;
    width: number;
    height: number;
    metadata?: CanvasNodeMetadata;
};

export type CanvasConnection = {
    id: string;
    fromNodeId: string;
    toNodeId: string;
};

export type CanvasAssistantReference = {
    id: string;
    type: CanvasNodeType;
    title: string;
    dataUrl?: string;
    storageKey?: string;
    text?: string;
};

export type CanvasAssistantImage = {
    id: string;
    dataUrl: string;
    storageKey?: string;
    prompt: string;
};

export type CanvasAssistantMessage = {
    id: string;
    role: "user" | "assistant" | "system" | "tool" | "error";
    title?: string;
    text: string;
    meta?: string;
    detail?: unknown;
    references?: CanvasAssistantReference[];
};

export type CanvasAssistantSession = {
    id: string;
    title: string;
    messages: CanvasAssistantMessage[];
    createdAt: string;
    updatedAt: string;
};

export type ConnectionHandle = {
    nodeId: string;
    handleType: "source" | "target";
};

export type SelectionBox = {
    startWorldX: number;
    startWorldY: number;
    currentWorldX: number;
    currentWorldY: number;
    additive: boolean;
    initialSelectedNodeIds: string[];
};

export type ContextMenuState =
    | {
          type: "node";
          x: number;
          y: number;
          nodeId: string;
      }
    | {
          type: "connection";
          x: number;
          y: number;
          connectionId: string;
      };
