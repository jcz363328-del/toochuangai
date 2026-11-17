import type { ReactNode } from "react";
import { useEffect, useRef } from "react";
import { App } from "antd";

import { createModelChannel, encodeChannelModel, useConfigStore, type ApiCallFormat, type ModelChannel } from "@/stores/use-config-store";

type BootstrapConfig = {
    configVersion?: string;
    channel?: Partial<ModelChannel>;
    channels?: Partial<ModelChannel>[];
    imageModel?: string;
    imageModelNext?: string;
    textModel?: string;
    videoModel?: string;
    audioModel?: string;
    imageModels?: string[];
    imageModelsNext?: string[];
    textModels?: string[];
    videoModels?: string[];
    audioModels?: string[];
};

type BootstrapResponse = {
    success?: boolean;
    config?: BootstrapConfig;
};

const BOOTSTRAP_CONFIG_VERSION_KEY = "infinite-canvas:bootstrap-config-version";

export function ClientRootInit({ children }: { children: ReactNode }) {
    const { message } = App.useApp();
    const handledConfigParams = useRef(false);
    const handledBootstrapConfig = useRef(false);
    const updateConfig = useConfigStore((state) => state.updateConfig);
    const config = useConfigStore((state) => state.config);
    const openConfigDialog = useConfigStore((state) => state.openConfigDialog);

    useEffect(() => {
        if (handledConfigParams.current) return;
        const searchParams = new URLSearchParams(window.location.search);
        const baseUrl = searchParams.get("baseUrl") || searchParams.get("baseurl");
        const apiKey = searchParams.get("apiKey") || searchParams.get("apikey");
        if (!baseUrl && !apiKey) return;
        handledConfigParams.current = true;
        searchParams.delete("baseUrl");
        searchParams.delete("baseurl");
        searchParams.delete("apiKey");
        searchParams.delete("apikey");
        window.history.replaceState(null, "", `${window.location.pathname}${searchParams.size ? `?${searchParams}` : ""}${window.location.hash}`);
        const firstChannel = config.channels[0];
        updateConfig(
            "channels",
            firstChannel
                ? config.channels.map((channel, index) =>
                      index === 0
                          ? {
                                ...channel,
                                ...(baseUrl ? { baseUrl } : {}),
                                ...(apiKey ? { apiKey } : {}),
                            }
                          : channel,
                  )
                : [createModelChannel({ id: "default", name: "默认渠道", baseUrl: baseUrl || undefined, apiKey: apiKey || "" })],
        );
        if (baseUrl) updateConfig("baseUrl", baseUrl);
        if (apiKey) updateConfig("apiKey", apiKey);
        openConfigDialog(false);
        message.success("已导入本地直连配置");
    }, [config.channels, message, openConfigDialog, updateConfig]);

    useEffect(() => {
        if (handledBootstrapConfig.current) return;
        handledBootstrapConfig.current = true;
        const basePath = import.meta.env.BASE_URL.endsWith("/") ? import.meta.env.BASE_URL : `${import.meta.env.BASE_URL}/`;
        const pageParams = new URLSearchParams(window.location.search);
        const bootstrapParams = new URLSearchParams();
        const authUser = pageParams.get("auth_user");
        const authToken = pageParams.get("auth_token");
        if (authUser) bootstrapParams.set("auth_user", authUser);
        if (authToken) bootstrapParams.set("auth_token", authToken);
        const bootstrapQuery = bootstrapParams.size ? `?${bootstrapParams.toString()}` : "";

        void fetch(`${basePath}api/bootstrap-config${bootstrapQuery}`, {
            credentials: "include",
            headers: { Accept: "application/json" },
        })
            .then(async (response) => {
                if (!response.ok) return null;
                return (await response.json()) as BootstrapResponse;
            })
            .then((payload) => {
                const bootstrap = payload?.config;
                if (!payload?.success || !bootstrap) return;
                if (
                    bootstrap.configVersion &&
                    localStorage.getItem(BOOTSTRAP_CONFIG_VERSION_KEY) === bootstrap.configVersion &&
                    config.channels.some((channel) => channel.apiKey.trim())
                ) {
                    return;
                }
                const rawChannels = (bootstrap.channels?.length ? bootstrap.channels : bootstrap.channel ? [bootstrap.channel] : []).filter(
                    (item): item is Partial<ModelChannel> => Boolean(item?.apiKey?.trim()),
                );
                if (!rawChannels.length) return;
                const channels = rawChannels.map((item, index) =>
                    createModelChannel({
                        ...item,
                        id: item.id || (index === 0 ? "default" : `channel-${index + 1}`),
                        apiFormat: (item.apiFormat || "openai") as ApiCallFormat,
                    }),
                );
                const channelForModel = (model: string) => channels.find((channel) => channel.models.includes(model)) || channels[0];
                const encode = (model?: string) => (model ? encodeChannelModel(channelForModel(model).id, model) : "");
                const encodeList = (models?: string[]) => (models || []).map((model) => encode(model));

                updateConfig("channels", channels);
                updateConfig("baseUrl", channels[0].baseUrl);
                updateConfig("apiKey", channels[0].apiKey);
                updateConfig("apiFormat", channels[0].apiFormat);
                updateConfig("models", channels.flatMap((channel) => channel.models.map((model) => encodeChannelModel(channel.id, model))));
                const imageModel = bootstrap.imageModelNext || bootstrap.imageModel;
                updateConfig("imageModels", encodeList(bootstrap.imageModelsNext || bootstrap.imageModels));
                updateConfig("textModels", encodeList(bootstrap.textModels));
                updateConfig("videoModels", encodeList(bootstrap.videoModels));
                updateConfig("audioModels", encodeList(bootstrap.audioModels));
                updateConfig("imageModel", encode(imageModel));
                updateConfig("textModel", encode(bootstrap.textModel));
                updateConfig("videoModel", encode(bootstrap.videoModel));
                updateConfig("audioModel", encode(bootstrap.audioModel));
                updateConfig("model", encode(imageModel));
                if (bootstrap.configVersion) localStorage.setItem(BOOTSTRAP_CONFIG_VERSION_KEY, bootstrap.configVersion);
                message.success("小哈生图配置已就绪");
            })
            .catch((error: unknown) => {
                console.warn("读取小哈配置失败", error);
            });
    }, [config.channels, message, updateConfig]);

    return <>{children}</>;
}
