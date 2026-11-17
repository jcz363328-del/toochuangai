'use client';

import { apiFetch } from '@/lib/apiClient';

import React, { useState, useCallback } from 'react';
import { Save, X, Users, MapPin, Film, Sparkles, BookOpen, Lightbulb, Target, User, Crosshair, RefreshCw, Palette, Edit3, Plus, Trash2 } from 'lucide-react';
import type { StageViewProps } from './types';
import StageActions from './StageActions';
import StageProgress from './StageProgress';

/* ─── 类型 ─── */

interface LoglineData {
  logline: string;
  who: string;
  goal: string;
  conflict: string;
  twist: string;
  theme: string;
}

interface ScriptCharacter {
  name: string;
  character_id?: string;
  description: string;
  age?: string;
  species?: string;
  occupation?: string;
}

interface ScriptSetting {
  name: string;
  description: string;
}

interface ScriptScene {
  scene_number: number;
  act?: number;
  location: string;
  characters: string[];
  plot: string;
}

interface ActCompleteData {
  act: number;
  act_name: string;
  characters: ScriptCharacter[];
  settings: ScriptSetting[];
  scenes: ScriptScene[];
}

interface ScriptEpisode {
  act_number: number;
  episode_number?: number;
  act_title: string;
  content: string;
}

interface ScriptData {
  title?: string;
  logline?: string;
  genre?: string[];
  characters?: ScriptCharacter[];
  settings?: ScriptSetting[];
  scenes?: ScriptScene[];
  episodes?: ScriptEpisode[];
  overall_style?: string;
  mood?: string;
  session_id?: string;
  [key: string]: any;
}

/* ─── Logline 六要素展示卡 ─── */
function LoglineSummaryBar({ logline }: { logline: LoglineData }) {
  const items = [
    { icon: Lightbulb, label: 'Logline', value: logline.logline, color: 'text-amber-600' },
    { icon: User, label: '主角', value: logline.who, color: 'text-blue-600' },
    { icon: Target, label: '目标', value: logline.goal, color: 'text-green-600' },
    { icon: Crosshair, label: '障碍', value: logline.conflict, color: 'text-red-500' },
    { icon: RefreshCw, label: '反转', value: logline.twist, color: 'text-purple-600' },
    { icon: Palette, label: '主题', value: logline.theme, color: 'text-cyan-600' },
  ];
  return (
    <div className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Lightbulb className="w-4 h-4 text-amber-500" />
        <span className="text-xs font-semibold text-amber-700">Logline 核心</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6 gap-3">
        {items.map(({ icon: Icon, label, value, color }) => (
          <div key={label} className="min-w-0">
            <div className={`flex items-center gap-1 mb-1 ${color}`}>
              <Icon className="w-3 h-3 flex-shrink-0" />
              <span className="text-[10px] font-semibold">{label}</span>
            </div>
            <p className="text-xs text-gray-600 leading-relaxed break-words">{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ScriptStage({ state, sessionId, onConfirm, onIntervene, onRegenerate, onUpdateArtifact, showConfirm, isRunning, hasPendingItems, hasNextStageStarted }: StageViewProps) {
  const data: ScriptData = state.artifact || {};

  const isLoglinePhase = data.phase === 'logline_selection' || data.phase === 'logline_confirm' || data.phase === 'mode_selection';

  const [showSmartContinueDialog, setShowSmartContinueDialog] = useState(false);
  const [smartContinueEpisodes, setSmartContinueEpisodes] = useState<number>(1);
  const [smartContinueIdea, setSmartContinueIdea] = useState<string>('');
  const [editingEpisodeIndex, setEditingEpisodeIndex] = useState<number | null>(null);
  const [savingEpisodeIndex, setSavingEpisodeIndex] = useState<number | null>(null);
  const [episodeDraft, setEpisodeDraft] = useState<{ title: string; content: string }>({ title: '', content: '' });
  const [editingCharacterIndex, setEditingCharacterIndex] = useState<number | null>(null);
  const [savingCharacterIndex, setSavingCharacterIndex] = useState<number | null>(null);
  const [characterDraft, setCharacterDraft] = useState({
    name: '',
    species: '',
    description: '',
  });
  const [editingSettingIndex, setEditingSettingIndex] = useState<number | null>(null);
  const [savingSettingIndex, setSavingSettingIndex] = useState<number | null>(null);
  const [settingDraft, setSettingDraft] = useState({ name: '', description: '' });
  const [deleteMode, setDeleteMode] = useState({
    characters: false,
    settings: false,
    episodes: false,
  });

  const handleSmartContinueConfirm = useCallback(() => {
    onIntervene({
      action: 'smart_continue',
      episodes_to_add: smartContinueEpisodes,
      sequel_idea: smartContinueIdea
    });
    setShowSmartContinueDialog(false);
    setSmartContinueIdea('');
    setSmartContinueEpisodes(1);
  }, [smartContinueEpisodes, smartContinueIdea, onIntervene]);

  const hasContent = Boolean(data.title || data.characters?.length || data.scenes?.length);

  const getEpisodeNumber = (ep: ScriptEpisode, index: number) =>
    Number(ep.episode_number || ep.act_number || index + 1);

  const patchScriptArtifact = async (patch: Record<string, any>) => {
    if (!sessionId) throw new Error('缺少会话 ID');
    const response = await apiFetch(`/api/project/${sessionId}/artifact/script_generation`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (!response.ok) throw new Error('保存剧本修改失败');
    return response.json();
  };

  const toggleDeleteMode = (key: keyof typeof deleteMode) => {
    setDeleteMode(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const createCharacter = async () => {
    const nextCharacter: ScriptCharacter = {
      name: '新角色',
      species: '',
      description: '请填写角色描述。',
    };
    const nextCharacters = [...(data.characters || []), nextCharacter];
    try {
      const result = await patchScriptArtifact({ characters: nextCharacters });
      const characters = result.artifact?.characters || nextCharacters;
      onUpdateArtifact?.({ characters });
      startCharacterEdit(characters[characters.length - 1], characters.length - 1);
    } catch (error) {
      console.error('新建角色失败:', error);
    }
  };

  const deleteCharacter = async (index: number) => {
    const target = data.characters?.[index];
    if (!target || !window.confirm(`确认删除角色「${target.name || index + 1}」吗？`)) return;
    try {
      const nextCharacters = (data.characters || []).filter((_, itemIndex) => itemIndex !== index);
      const result = await patchScriptArtifact({ characters: nextCharacters });
      onUpdateArtifact?.({ characters: result.artifact?.characters || nextCharacters });
      if (editingCharacterIndex === index) cancelCharacterEdit();
    } catch (error) {
      console.error('删除角色失败:', error);
    }
  };

  const createSetting = async () => {
    const nextSetting: ScriptSetting = {
      name: '新场景',
      description: '请填写场景描述。',
    };
    const nextSettings = [...(data.settings || []), nextSetting];
    try {
      const result = await patchScriptArtifact({ settings: nextSettings });
      const settings = result.artifact?.settings || nextSettings;
      onUpdateArtifact?.({ settings });
      startSettingEdit(settings[settings.length - 1], settings.length - 1);
    } catch (error) {
      console.error('新建场景失败:', error);
    }
  };

  const deleteSetting = async (index: number) => {
    const target = data.settings?.[index];
    if (!target || !window.confirm(`确认删除场景「${target.name || index + 1}」吗？`)) return;
    try {
      const nextSettings = (data.settings || []).filter((_, itemIndex) => itemIndex !== index);
      const result = await patchScriptArtifact({ settings: nextSettings });
      onUpdateArtifact?.({ settings: result.artifact?.settings || nextSettings });
      if (editingSettingIndex === index) cancelSettingEdit();
    } catch (error) {
      console.error('删除场景失败:', error);
    }
  };

  const createEpisode = async () => {
    const nextNumber = (data.episodes || []).reduce((max, ep, index) => {
      return Math.max(max, getEpisodeNumber(ep, index));
    }, 0) + 1;
    const nextEpisode: ScriptEpisode = {
      act_number: nextNumber,
      episode_number: nextNumber,
      act_title: '新剧集',
      content: '请填写本集剧情。',
    };
    const nextEpisodes = [...(data.episodes || []), nextEpisode];
    try {
      const result = await patchScriptArtifact({ episodes: nextEpisodes });
      const episodes = result.artifact?.episodes || nextEpisodes;
      onUpdateArtifact?.({ episodes });
      startEpisodeEdit(episodes[episodes.length - 1], episodes.length - 1);
    } catch (error) {
      console.error('新建分集失败:', error);
    }
  };

  const deleteEpisode = async (index: number) => {
    const target = data.episodes?.[index];
    if (!target || !window.confirm(`确认删除第 ${getEpisodeNumber(target, index)} 集「${target.act_title || ''}」吗？`)) return;
    try {
      const nextEpisodes = (data.episodes || []).filter((_, itemIndex) => itemIndex !== index);
      const result = await patchScriptArtifact({ episodes: nextEpisodes });
      onUpdateArtifact?.({ episodes: result.artifact?.episodes || nextEpisodes });
      if (editingEpisodeIndex === index) cancelEpisodeEdit();
    } catch (error) {
      console.error('删除分集失败:', error);
    }
  };

  const startEpisodeEdit = (ep: ScriptEpisode, index: number) => {
    setEditingEpisodeIndex(index);
    setEpisodeDraft({
      title: ep.act_title || '',
      content: ep.content || '',
    });
  };

  const cancelEpisodeEdit = () => {
    setEditingEpisodeIndex(null);
    setEpisodeDraft({ title: '', content: '' });
  };

  const saveEpisodeEdit = async (ep: ScriptEpisode, index: number) => {
    if (!sessionId || savingEpisodeIndex !== null) return;
    setSavingEpisodeIndex(index);
    try {
      const nextEpisodes = (data.episodes || []).map((item, itemIndex) => {
        if (itemIndex !== index) return item;
        return {
          ...item,
          act_title: episodeDraft.title,
          ...(Object.prototype.hasOwnProperty.call(item, 'title') ? { title: episodeDraft.title } : {}),
          content: episodeDraft.content,
        };
      });
      const result = await patchScriptArtifact({ episodes: nextEpisodes });
      if (result.artifact?.episodes) {
        onUpdateArtifact?.({ episodes: result.artifact.episodes });
      }
      cancelEpisodeEdit();
    } catch (error) {
      console.error('保存分集剧本失败:', error);
    } finally {
      setSavingEpisodeIndex(null);
    }
  };

  const startCharacterEdit = (character: ScriptCharacter, index: number) => {
    setEditingCharacterIndex(index);
    setEditingSettingIndex(null);
    setCharacterDraft({
      name: character.name || '',
      species: character.species || '',
      description: character.description || '',
    });
  };

  const cancelCharacterEdit = () => {
    setEditingCharacterIndex(null);
    setCharacterDraft({
      name: '',
      species: '',
      description: '',
    });
  };

  const saveCharacterEdit = async (index: number) => {
    if (savingCharacterIndex !== null) return;
    setSavingCharacterIndex(index);
    try {
      const nextCharacters = (data.characters || []).map((character, itemIndex) => {
        if (itemIndex !== index) return character;
        const restCharacter = { ...(character as ScriptCharacter & Record<string, any>) };
        delete restCharacter.role;
        delete restCharacter.personality;
        delete restCharacter.motivation;
        delete restCharacter.arc_description;
        return {
          ...restCharacter,
          name: characterDraft.name,
          species: characterDraft.species,
          description: characterDraft.description,
        };
      });
      const result = await patchScriptArtifact({ characters: nextCharacters });
      if (result.artifact?.characters) {
        onUpdateArtifact?.({ characters: result.artifact.characters });
      }
      cancelCharacterEdit();
    } catch (error) {
      console.error('保存角色失败:', error);
    } finally {
      setSavingCharacterIndex(null);
    }
  };

  const startSettingEdit = (setting: ScriptSetting, index: number) => {
    setEditingSettingIndex(index);
    setEditingCharacterIndex(null);
    setSettingDraft({
      name: setting.name || '',
      description: setting.description || '',
    });
  };

  const cancelSettingEdit = () => {
    setEditingSettingIndex(null);
    setSettingDraft({ name: '', description: '' });
  };

  const saveSettingEdit = async (index: number) => {
    if (savingSettingIndex !== null) return;
    setSavingSettingIndex(index);
    try {
      const nextSettings = (data.settings || []).map((setting, itemIndex) => (
        itemIndex === index
          ? { ...setting, name: settingDraft.name, description: settingDraft.description }
          : setting
      ));
      const result = await patchScriptArtifact({ settings: nextSettings });
      if (result.artifact?.settings) {
        onUpdateArtifact?.({ settings: result.artifact.settings });
      }
      cancelSettingEdit();
    } catch (error) {
      console.error('保存场景失败:', error);
    } finally {
      setSavingSettingIndex(null);
    }
  };

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex-1 min-w-0 overflow-y-auto p-4 sm:p-6">

        {/* 标题栏 */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-1">
          <h2 className="text-lg font-semibold text-gray-800">剧本生成</h2>
        </div>
        <p className="text-sm text-gray-500 mb-6">多轮 LLM 交互，生成结构化剧本数据</p>

        {/* 运行中 - 进度条 & 已选 Logline & 增量生成结果 */}
        {state.status === 'running' && (
          <>
            {data.selected_logline && (
              <div className="mb-4">
                <LoglineSummaryBar logline={data.selected_logline as LoglineData} />
              </div>
            )}

            {/* 节拍表展示 */}
            {data.beat_sheet && (
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <BookOpen className="w-4 h-4 text-orange-500" />
                  <h3 className="text-sm font-semibold text-gray-700">节拍表 (Beat Sheet)</h3>
                </div>
                <div className="bg-white border border-gray-200 rounded-xl p-4">
                  <pre className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap font-sans">{data.beat_sheet as string}</pre>
                </div>
              </div>
            )}

            {/* 逐幕完成的分场结果 */}
            {data.completed_acts && (data.completed_acts as ActCompleteData[]).length > 0 && (
              <div className="mb-4 space-y-4">
                {(data.completed_acts as ActCompleteData[]).map((actData) => (
                  <div key={actData.act}>
                    {/* 幕分隔线 */}
                    <div className="flex items-center gap-3 mb-3">
                      <div className="flex-1 h-px bg-gradient-to-r from-purple-200 to-transparent" />
                      <span className="px-3 py-1 bg-purple-50 text-purple-600 text-xs font-semibold rounded-full whitespace-nowrap">
                        第{actData.act}幕 — {actData.act_name}
                      </span>
                      <div className="flex-1 h-px bg-gradient-to-l from-purple-200 to-transparent" />
                    </div>

                    {/* 本幕场景 */}
                    <div className="space-y-2">
                      {actData.scenes.map((sc, i) => (
                        <div key={i} className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow">
                          <div className="flex items-center gap-3 mb-2">
                            <span className="flex items-center justify-center w-7 h-7 rounded-full bg-purple-100 text-purple-700 text-xs font-bold flex-shrink-0">{sc.scene_number}</span>
                            <span className="px-2 py-0.5 bg-green-50 text-green-600 text-xs rounded-full">{sc.location}</span>
                            <div className="flex flex-wrap gap-1">
                              {(sc.characters || []).map((c: any, ci: number) => (
                                <span key={ci} className="px-2 py-0.5 bg-blue-50 text-blue-600 text-xs rounded-full">{c}</span>
                              ))}
                            </div>
                          </div>
                          <p className="text-sm text-gray-600 leading-relaxed pl-10">{sc.plot}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <StageProgress message={state.progressMessage} fallback="正在生成剧本..." progress={state.progress} color="blue" />
          </>
        )}

        {/* 错误 */}
        {state.error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 p-4 rounded-xl mb-4">{state.error}</div>
        )}

        {/* ===== Logline 选择/确认阶段 ===== */}
        {isLoglinePhase && state.status === 'waiting' && (
          <div className="space-y-4">
            {/* 3 个 Logline 选项卡 */}
            {data.phase === 'logline_selection' && data.logline_options && (
              <>
                <div className="flex items-center gap-2 mb-2">
                  <Lightbulb className="w-4 h-4 text-amber-500" />
                  <h3 className="text-sm font-semibold text-gray-700">选择一个 Logline 方案</h3>
                  <span className="text-xs text-gray-400">点击卡片以选择</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {(data.logline_options as LoglineData[]).map((opt, i) => (
                    <button
                      key={i}
                      onClick={() => onIntervene({ selected_logline: opt })}
                      className="text-left p-4 bg-white border border-gray-200 rounded-xl hover:border-blue-400 hover:shadow-md transition-all group cursor-pointer"
                    >
                      <p className="text-sm font-medium text-gray-800 group-hover:text-blue-600 mb-3 leading-relaxed">
                        {opt.logline}
                      </p>
                      <div className="space-y-1.5 text-xs text-gray-500">
                        <p><span className="text-gray-600 font-medium">主角:</span> {opt.who}</p>
                        <p><span className="text-gray-600 font-medium">目标:</span> {opt.goal}</p>
                        <p><span className="text-gray-600 font-medium">障碍:</span> {opt.conflict}</p>
                        <p><span className="text-gray-600 font-medium">反转:</span> {opt.twist}</p>
                        <p><span className="text-gray-600 font-medium">主题:</span> {opt.theme}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </>
            )}

            {/* 单个 Logline 确认 */}
            {data.phase === 'logline_confirm' && data.logline_summary && (
              <>
                <div className="flex items-center gap-2 mb-2">
                  <Lightbulb className="w-4 h-4 text-amber-500" />
                  <h3 className="text-sm font-semibold text-gray-700">Logline 提取结果</h3>
                </div>
                <LoglineSummaryBar logline={data.logline_summary as LoglineData} />
                <div className="flex justify-center pt-2">
                  <button
                    onClick={() => onIntervene({ selected_logline: data.logline_summary })}
                    className="flex items-center gap-2 px-5 py-2.5 bg-blue-500 text-white rounded-lg text-sm font-medium hover:bg-blue-600 transition-colors"
                  >
                    <Sparkles className="w-4 h-4" />
                    确认 Logline 并生成剧本
                  </button>
                </div>
              </>
            )}

            {/* 创作模式选择 */}
            {data.phase === 'mode_selection' && (
              <>
                {data.selected_logline && (
                  <div className="mb-4">
                    <LoglineSummaryBar logline={data.selected_logline as LoglineData} />
                  </div>
                )}
                <div className="flex items-center gap-2 mb-3">
                  <Film className="w-4 h-4 text-purple-500" />
                  <h3 className="text-sm font-semibold text-gray-700">选择创作模式</h3>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <button
                    onClick={() => onIntervene({ selected_mode: 'movie' })}
                    className="text-left p-5 bg-white border-2 border-gray-200 rounded-xl hover:border-purple-400 hover:shadow-lg transition-all group cursor-pointer"
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <span className="flex items-center justify-center w-10 h-10 rounded-xl bg-purple-100 text-purple-600 text-lg">🎬</span>
                      <span className="text-base font-semibold text-gray-800 group-hover:text-purple-600">电影模式</span>
                    </div>
                    <p className="text-sm text-gray-600 leading-relaxed mb-3">
                      按照四幕结构生成完整情节，叙事连贯丰富，有完整的起承转合。
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      <span className="px-2 py-0.5 bg-purple-50 text-purple-500 text-xs rounded-full">四幕结构</span>
                      <span className="px-2 py-0.5 bg-purple-50 text-purple-500 text-xs rounded-full">叙事完整</span>
                      <span className="px-2 py-0.5 bg-purple-50 text-purple-500 text-xs rounded-full">情节丰富</span>
                    </div>
                  </button>
                  <button
                    onClick={() => onIntervene({ selected_mode: 'micro' })}
                    className="text-left p-5 bg-white border-2 border-gray-200 rounded-xl hover:border-cyan-400 hover:shadow-lg transition-all group cursor-pointer"
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <span className="flex items-center justify-center w-10 h-10 rounded-xl bg-cyan-100 text-cyan-600 text-lg">🎞️</span>
                      <span className="text-base font-semibold text-gray-800 group-hover:text-cyan-600">微电影模式</span>
                    </div>
                    <p className="text-sm text-gray-600 leading-relaxed mb-3">
                      所有内容生成在一幕内，叙事节奏快，情节紧凑，适合短片创作。
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      <span className="px-2 py-0.5 bg-cyan-50 text-cyan-500 text-xs rounded-full">单幕结构</span>
                      <span className="px-2 py-0.5 bg-cyan-50 text-cyan-500 text-xs rounded-full">节奏紧凑</span>
                      <span className="px-2 py-0.5 bg-cyan-50 text-cyan-500 text-xs rounded-full">3-6场景</span>
                    </div>
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* ===== 查看模式 ===== */}
        {hasContent && (
          <div className="space-y-8">

            {/* Logline 六要素摘要 */}
            {data.logline_data && (
              <LoglineSummaryBar logline={data.logline_data as LoglineData} />
            )}

            {/* 标题 / Logline / 标签 */}
            {data.title && (
              <section className="bg-white border border-gray-200 rounded-xl p-5">
                <h3 className="text-xl font-bold text-gray-800 mb-2">{data.title}</h3>
                {data.logline && <p className="text-sm text-gray-500 mb-3">{data.logline}</p>}
                <div className="flex flex-wrap gap-1.5">
                  {data.genre?.map((g, i) => (
                    <span key={i} className="px-2.5 py-0.5 bg-violet-50 text-violet-600 text-xs rounded-full font-medium">{g}</span>
                  ))}
                  {data.mood && <span className="px-2.5 py-0.5 bg-pink-50 text-pink-600 text-xs rounded-full font-medium">{data.mood}</span>}
                  {data.overall_style && <span className="px-2.5 py-0.5 bg-cyan-50 text-cyan-600 text-xs rounded-full font-medium">{data.overall_style}</span>}
                </div>
              </section>
            )}

            {/* 故事梗概 */}
            {data.logline && (
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <BookOpen className="w-4 h-4 text-orange-500" />
                  <h3 className="text-sm font-semibold text-gray-700">故事梗概</h3>
                </div>
                <div className="bg-white border border-gray-200 rounded-xl p-5">
                  <p className="text-sm text-gray-600 leading-relaxed">{data.logline}</p>
                </div>
              </section>
            )}

            {/* 角色 */}
            {Array.isArray(data.characters) && (
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <Users className="w-4 h-4 text-blue-500" />
                  <h3 className="text-sm font-semibold text-gray-700">角色</h3>
                  <button
                    onClick={createCharacter}
                    className="ml-2 inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 transition-colors"
                  >
                    <Plus className="w-3 h-3" />
                    新建
                  </button>
                  <button
                    onClick={() => toggleDeleteMode('characters')}
                    className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
                      deleteMode.characters
                        ? 'text-red-600 bg-red-50 hover:bg-red-100'
                        : 'text-gray-500 bg-gray-100 hover:bg-gray-200'
                    }`}
                  >
                    <Trash2 className="w-3 h-3" />
                    删除
                  </button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {data.characters.map((c, i) => {
                    const isCharacterEditing = editingCharacterIndex === i;
                    const isCharacterSaving = savingCharacterIndex === i;
                    return (
                    <div key={i} className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow">
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="min-w-0">
                          {isCharacterEditing ? (
                            <input
                              value={characterDraft.name}
                              onChange={e => setCharacterDraft(prev => ({ ...prev, name: e.target.value }))}
                              className="w-full rounded-lg border border-blue-100 px-2 py-1 text-sm font-medium text-gray-800 outline-none focus:ring-2 focus:ring-blue-200"
                            />
                          ) : (
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium text-gray-800">{c.name}</span>
                              {c.species && c.species !== '人类' && c.species !== 'human' && (
                                <span className="px-1.5 py-0.5 bg-emerald-50 text-emerald-600 text-[10px] rounded">{c.species}</span>
                              )}
                            </div>
                          )}
                        </div>
                        {isCharacterEditing ? (
                          <div className="flex flex-shrink-0 items-center gap-1">
                            <button
                              onClick={cancelCharacterEdit}
                              disabled={isCharacterSaving}
                              className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-gray-500 hover:bg-gray-100 disabled:opacity-50"
                            >
                              <X className="w-3 h-3" />取消
                            </button>
                            <button
                              onClick={() => saveCharacterEdit(i)}
                              disabled={isCharacterSaving || !characterDraft.name.trim() || !characterDraft.description.trim()}
                              className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-white bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300 disabled:cursor-not-allowed"
                            >
                              <Save className="w-3 h-3" />{isCharacterSaving ? '保存中' : '保存'}
                            </button>
                          </div>
                        ) : deleteMode.characters ? (
                          <button
                            onClick={() => deleteCharacter(i)}
                            className="flex flex-shrink-0 items-center justify-center w-7 h-7 rounded-lg text-red-600 bg-red-50 hover:bg-red-100 transition-colors"
                            title="删除角色"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        ) : (
                          <button
                            onClick={() => startCharacterEdit(c, i)}
                            className="flex flex-shrink-0 items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 transition-colors"
                          >
                            <Edit3 className="w-3 h-3" />修改
                          </button>
                        )}
                      </div>
                      {isCharacterEditing ? (
                        <div className="space-y-2">
                          <label className="flex flex-col gap-1 text-xs">
                            <span className="text-gray-500 font-medium">物种/类型</span>
                            <input
                              value={characterDraft.species}
                              onChange={e => setCharacterDraft(prev => ({ ...prev, species: e.target.value }))}
                              className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm text-gray-700 outline-none focus:ring-2 focus:ring-blue-200"
                            />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">
                            <span className="text-gray-500 font-medium">描述</span>
                            <textarea
                              value={characterDraft.description}
                              onChange={e => setCharacterDraft(prev => ({ ...prev, description: e.target.value }))}
                              rows={3}
                              className="resize-y rounded-lg border border-gray-200 px-2 py-1.5 text-sm text-gray-700 outline-none focus:ring-2 focus:ring-blue-200"
                            />
                          </label>
                        </div>
                      ) : (
                        <p className="text-sm text-gray-500 leading-relaxed mb-2">{c.description}</p>
                      )}
                    </div>
                    );
                  })}
                </div>
              </section>
            )}

            {/* 场景设置 */}
            {Array.isArray(data.settings) && (
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <MapPin className="w-4 h-4 text-green-500" />
                  <h3 className="text-sm font-semibold text-gray-700">场景</h3>
                  <button
                    onClick={createSetting}
                    className="ml-2 inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-green-600 bg-green-50 hover:bg-green-100 transition-colors"
                  >
                    <Plus className="w-3 h-3" />
                    新建
                  </button>
                  <button
                    onClick={() => toggleDeleteMode('settings')}
                    className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
                      deleteMode.settings
                        ? 'text-red-600 bg-red-50 hover:bg-red-100'
                        : 'text-gray-500 bg-gray-100 hover:bg-gray-200'
                    }`}
                  >
                    <Trash2 className="w-3 h-3" />
                    删除
                  </button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {data.settings.map((s, i) => {
                    const isSettingEditing = editingSettingIndex === i;
                    const isSettingSaving = savingSettingIndex === i;
                    return (
                    <div key={i} className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow">
                      <div className="flex items-start justify-between gap-2 mb-2">
                        {isSettingEditing ? (
                          <input
                            value={settingDraft.name}
                            onChange={e => setSettingDraft(prev => ({ ...prev, name: e.target.value }))}
                            className="min-w-0 flex-1 rounded-lg border border-green-100 px-2 py-1 text-sm font-medium text-gray-800 outline-none focus:ring-2 focus:ring-green-200"
                          />
                        ) : (
                          <div className="font-medium text-gray-800">{s.name}</div>
                        )}
                        {isSettingEditing ? (
                          <div className="flex flex-shrink-0 items-center gap-1">
                            <button
                              onClick={cancelSettingEdit}
                              disabled={isSettingSaving}
                              className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-gray-500 hover:bg-gray-100 disabled:opacity-50"
                            >
                              <X className="w-3 h-3" />取消
                            </button>
                            <button
                              onClick={() => saveSettingEdit(i)}
                              disabled={isSettingSaving || !settingDraft.name.trim() || !settingDraft.description.trim()}
                              className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-white bg-green-500 hover:bg-green-600 disabled:bg-green-300 disabled:cursor-not-allowed"
                            >
                              <Save className="w-3 h-3" />{isSettingSaving ? '保存中' : '保存'}
                            </button>
                          </div>
                        ) : deleteMode.settings ? (
                          <button
                            onClick={() => deleteSetting(i)}
                            className="flex flex-shrink-0 items-center justify-center w-7 h-7 rounded-lg text-red-600 bg-red-50 hover:bg-red-100 transition-colors"
                            title="删除场景"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        ) : (
                          <button
                            onClick={() => startSettingEdit(s, i)}
                            className="flex flex-shrink-0 items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-green-600 bg-green-50 hover:bg-green-100 transition-colors"
                          >
                            <Edit3 className="w-3 h-3" />修改
                          </button>
                        )}
                      </div>
                      {isSettingEditing ? (
                        <textarea
                          value={settingDraft.description}
                          onChange={e => setSettingDraft(prev => ({ ...prev, description: e.target.value }))}
                          rows={4}
                          className="w-full resize-y rounded-lg border border-gray-200 px-2 py-1.5 text-sm text-gray-700 outline-none focus:ring-2 focus:ring-green-200"
                        />
                      ) : (
                        <p className="text-sm text-gray-500 leading-relaxed">{s.description}</p>
                      )}
                    </div>
                    );
                  })}
                </div>
              </section>
            )}

            {/* 故事线 */}
            {Array.isArray(data.episodes) ? (
          <section className="bg-gray-50 p-4 rounded-xl border border-gray-100">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Film className="w-5 h-5 text-purple-500" />
                <h3 className="text-sm font-bold text-gray-800">分集剧本</h3>
                <button
                  onClick={createEpisode}
                  className="ml-2 inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-purple-600 bg-purple-50 hover:bg-purple-100 transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  新建
                </button>
                <button
                  onClick={() => toggleDeleteMode('episodes')}
                  className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
                    deleteMode.episodes
                      ? 'text-red-600 bg-red-50 hover:bg-red-100'
                      : 'text-gray-500 bg-gray-100 hover:bg-gray-200'
                  }`}
                >
                  <Trash2 className="w-3 h-3" />
                  删除
                </button>
              </div>
            </div>
            <div className="space-y-6">
              {data.episodes.map((ep, i) => {
                const episodeNumber = getEpisodeNumber(ep, i);
                const isEpisodeEditing = editingEpisodeIndex === i;
                const isSavingEpisode = savingEpisodeIndex === i;
                return (
                <div key={i} className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow">
                  <div className="bg-gradient-to-r from-purple-50 to-white px-4 py-3 border-b border-purple-100 flex flex-wrap items-center justify-between gap-3">
                    {isEpisodeEditing ? (
                      <div className="flex min-w-0 flex-1 items-center gap-2">
                        <span className="font-bold text-purple-800 whitespace-nowrap">第 {episodeNumber} 集：</span>
                        <input
                          value={episodeDraft.title}
                          onChange={e => setEpisodeDraft(prev => ({ ...prev, title: e.target.value }))}
                          className="min-w-0 flex-1 rounded-lg border border-purple-100 bg-white px-3 py-1.5 text-sm font-bold text-purple-800 outline-none focus:ring-2 focus:ring-purple-200"
                        />
                      </div>
                    ) : (
                      <h4 className="font-bold text-purple-800">第 {episodeNumber} 集：{ep.act_title}</h4>
                    )}
                    {isEpisodeEditing ? (
                      <div className="flex items-center gap-2">
                        <button
                          onClick={cancelEpisodeEdit}
                          disabled={isSavingEpisode}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-gray-500 hover:bg-gray-100 disabled:opacity-50"
                        >
                          <X className="w-3.5 h-3.5" />
                          取消
                        </button>
                        <button
                          onClick={() => saveEpisodeEdit(ep, i)}
                          disabled={isSavingEpisode || !episodeDraft.content.trim()}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-white bg-purple-500 hover:bg-purple-600 disabled:bg-purple-300 disabled:cursor-not-allowed"
                        >
                          <Save className="w-3.5 h-3.5" />
                          {isSavingEpisode ? '保存中' : '保存'}
                        </button>
                      </div>
                    ) : deleteMode.episodes ? (
                      <button
                        onClick={() => deleteEpisode(i)}
                        className="flex items-center justify-center w-8 h-8 rounded-lg text-red-600 bg-red-50 hover:bg-red-100 transition-colors"
                        title="删除分集"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    ) : (
                      <button
                        onClick={() => startEpisodeEdit(ep, i)}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-purple-600 bg-purple-50 hover:bg-purple-100 transition-colors"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                        修改
                      </button>
                    )}
                  </div>
                  {isEpisodeEditing ? (
                    <div className="p-5">
                      <textarea
                        value={episodeDraft.content}
                        onChange={e => setEpisodeDraft(prev => ({ ...prev, content: e.target.value }))}
                        rows={12}
                        className="w-full resize-y rounded-xl border border-gray-200 bg-gray-50 p-4 text-[15px] leading-relaxed text-gray-700 outline-none focus:bg-white focus:ring-2 focus:ring-purple-200"
                      />
                    </div>
                  ) : (
                    <div className="p-5 text-gray-700 whitespace-pre-wrap leading-relaxed text-[15px]">
                      {ep.content}
                    </div>
                  )}
                </div>
                );
              })}
            </div>
          </section>
        ) : data.scenes && data.scenes.length > 0 && (
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <Film className="w-4 h-4 text-purple-500" />
                  <h3 className="text-sm font-semibold text-gray-700">故事线 ({data.scenes.length} 场)</h3>
                </div>
                <div className="space-y-3">
                  {data.scenes.map((sc, i) => {
                    // 幕分隔线：当场景有 act 字段，且是第一场或与上一场不同幕时显示
                    const showActSep = sc.act != null && (i === 0 || data.scenes![i - 1].act !== sc.act);
                    const actNames: Record<number, string> = { 1: '激励事件', 2: '进入新世界', 3: '灵魂黑夜', 4: '高潮决战' };
                    return (
                      <React.Fragment key={i}>
                        {showActSep && (
                          <div className="flex items-center gap-3 pt-2">
                            <div className="flex-1 h-px bg-gradient-to-r from-purple-200 to-transparent" />
                            <span className="px-3 py-1 bg-purple-50 text-purple-600 text-xs font-semibold rounded-full whitespace-nowrap">
                              第{sc.act}幕 — {actNames[sc.act!] || ''}
                            </span>
                            <div className="flex-1 h-px bg-gradient-to-l from-purple-200 to-transparent" />
                          </div>
                        )}
                        <div className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow">
                          <div className="flex items-center gap-3 mb-2">
                            <span className="flex items-center justify-center w-7 h-7 rounded-full bg-purple-100 text-purple-700 text-xs font-bold flex-shrink-0">{sc.scene_number}</span>
                            <span className="px-2 py-0.5 bg-green-50 text-green-600 text-xs rounded-full">{sc.location}</span>
                            <div className="flex flex-wrap gap-1">
                              {(sc.characters || []).map((c: any, ci: number) => (
                                <span key={ci} className="px-2 py-0.5 bg-blue-50 text-blue-600 text-xs rounded-full">{c}</span>
                              ))}
                            </div>
                          </div>
                          <p className="text-sm text-gray-600 leading-relaxed pl-10">{sc.plot}</p>
                        </div>
                      </React.Fragment>
                    );
                  })}
                </div>
              </section>
            )}

            {/* ===== 智能续写 UI ===== */}
            {!data.new_episodes || data.new_episodes.length === 0 ? (
              data.episodes && data.episodes.length > 0 && state.status !== 'running' && (
                <div className="mt-8 flex justify-center">
                  <button
                    onClick={() => setShowSmartContinueDialog(true)}
                    className="flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-purple-500 to-purple-600 text-white rounded-full shadow-md hover:shadow-lg hover:from-purple-600 hover:to-purple-700 transition-all font-medium text-sm"
                  >
                    <Sparkles className="w-4 h-4" />
                    智能续写
                  </button>
                </div>
              )
            ) : (
              <div className="mt-8 space-y-6">
                <div className="relative flex py-5 items-center">
                  <div className="flex-grow border-t border-purple-300 border-dashed"></div>
                  <span className="flex-shrink-0 mx-4 text-purple-600 font-bold text-sm bg-purple-50 px-4 py-1 rounded-full shadow-sm">续集</span>
                  <div className="flex-grow border-t border-purple-300 border-dashed"></div>
                </div>
                
                {data.new_characters && data.new_characters.length > 0 && (
                  <div className="bg-amber-50 p-4 rounded-xl border border-amber-200 shadow-sm flex flex-col gap-3">
                    <h4 className="text-sm font-bold text-amber-800 flex items-center gap-2">
                      <Users className="w-4 h-4" /> 新增角色
                    </h4>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                      {data.new_characters.map((c: any, i: number) => (
                        <div key={i} className="bg-white p-3 rounded-lg border border-amber-100 shadow-sm flex flex-col gap-1">
                          <div className="font-bold text-amber-900 text-sm">{c.name}</div>
                          <p className="text-[11px] text-gray-600 line-clamp-2 md:line-clamp-none">{c.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {data.new_settings && data.new_settings.length > 0 && (
                  <div className="bg-emerald-50 p-4 rounded-xl border border-emerald-200 shadow-sm flex flex-col gap-3">
                    <h4 className="text-sm font-bold text-emerald-800 flex items-center gap-2">
                      <MapPin className="w-4 h-4" /> 新增场景
                    </h4>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                      {data.new_settings.map((s: any, i: number) => (
                        <div key={i} className="bg-white p-3 rounded-lg border border-emerald-100 shadow-sm flex flex-col gap-1">
                          <div className="font-bold text-emerald-900 text-sm">{s.name}</div>
                          <p className="text-[11px] text-gray-600 line-clamp-2 md:line-clamp-none">{s.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="space-y-6">
                  {data.new_episodes.map((ep: any, i: number) => (
                    <div key={`new-${i}`} className="bg-purple-50 border-2 border-purple-300 rounded-xl overflow-hidden shadow-md">
                      <div className="bg-gradient-to-r from-purple-200 to-purple-100 px-4 py-3 flex items-center justify-between border-b border-purple-200/50">
                        <h4 className="font-bold text-purple-900">第 {ep.episode_number || (data.episodes ? data.episodes.length + i + 1 : i + 1)} 集：{ep.act_title}</h4>
                        <span className="text-[10px] font-bold text-purple-700 bg-purple-200/50 px-2 py-0.5 rounded shadow-sm tracking-wider">NEW EPISODE</span>
                      </div>
                      <div className="p-5 text-gray-800 whitespace-pre-wrap leading-relaxed text-[15px] bg-white/80">
                        {ep.content}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="flex justify-end gap-3 mt-4">
                  <button
                    onClick={() => onIntervene({ action: 'delete_continue' })}
                    className="px-5 py-2 text-red-600 bg-red-50 hover:bg-red-100 rounded-lg text-sm font-medium transition-colors border border-red-200"
                  >
                    删除新剧集
                  </button>
                  <button
                    onClick={() => onIntervene({ action: 'confirm_continue' })}
                    className="flex items-center gap-2 px-5 py-2 bg-gradient-to-r from-purple-600 to-purple-700 text-white rounded-lg text-sm font-medium hover:from-purple-700 hover:to-purple-800 transition-colors shadow-sm"
                  >
                    <Save className="w-4 h-4" />
                    保存新剧集
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 等待状态 */}
        {state.status === 'pending' && (
          <div className="text-center text-gray-400 text-sm py-20">等待生成...</div>
        )}
      </div>

      {!isLoglinePhase && (
        <StageActions
          status={state.status}
          onConfirm={onConfirm}
          showConfirm={showConfirm}
          onRegenerate={onRegenerate}
          stageId="script_generation"
          hasPendingItems={hasPendingItems}
          hasNextStageStarted={hasNextStageStarted}
          isRunning={isRunning}
        />
      )}

      {/* ===== 智能续写弹窗 ===== */}
      {showSmartContinueDialog && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm shadow-2xl transition-opacity duration-200">
          <div className="bg-white rounded-2xl w-[min(480px,calc(100vw-2rem))] p-6 shadow-2xl animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold text-gray-800 mb-5 flex items-center gap-2 border-b border-gray-100 pb-3">
              <Sparkles className="w-5 h-5 text-purple-500" />
              智能续写设置
            </h3>
            
            <div className="space-y-5">
              <div>
                <label className="block text-[13px] font-bold text-gray-600 mb-2 uppercase tracking-wide">一次续写剧集数</label>
                <div className="flex gap-3">
                  {[1, 2, 3].map((num) => (
                    <button
                      key={num}
                      onClick={() => setSmartContinueEpisodes(num)}
                      className={`flex-1 py-2.5 px-4 rounded-xl font-bold text-sm transition-all border outline-none ${
                        smartContinueEpisodes === num 
                          ? 'bg-purple-50 border-purple-500 text-purple-700 shadow-[0_0_0_2px_rgba(168,85,247,0.1)]'
                          : 'bg-white border-gray-200 text-gray-500 hover:bg-gray-50 hover:border-gray-300'
                      }`}
                    >
                      {num} 集
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-[13px] font-bold text-gray-600 mb-2 flex items-center gap-2">
                  后续剧情想法主线 <span className="text-[10px] font-medium text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">(可选)</span>
                </label>
                <textarea 
                  value={smartContinueIdea}
                  onChange={(e) => setSmartContinueIdea(e.target.value)}
                  placeholder="如果留空，AI 将自动为您生成后续的续写灵感主线。"
                  className="w-full h-32 border border-gray-200 rounded-xl p-3 text-[14px] text-gray-700 focus:outline-none focus:border-purple-400 focus:ring-2 focus:ring-purple-500/20 resize-none transition-all placeholder:text-gray-400 bg-gray-50/50 focus:bg-white"
                ></textarea>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-8">
              <button 
                onClick={() => setShowSmartContinueDialog(false)}
                className="px-5 py-2.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-xl text-sm font-bold transition-colors outline-none"
              >
                取消
              </button>
              <button 
                onClick={handleSmartContinueConfirm}
                className="px-6 py-2.5 bg-gradient-to-r from-purple-500 to-purple-600 text-white rounded-xl text-sm font-bold hover:from-purple-600 hover:to-purple-700 transition-all shadow-md group flex items-center justify-center gap-2 outline-none hover:shadow-lg"
              >
                <Sparkles className="w-4 h-4 opacity-70" />
                确认生成
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
