import { ModelType } from './model-types';

export interface FilenameKeyword {
  id: number;
  keyword: string;
  base_model: string | null;
  model_type: string | null;
  sort_order: number;
}

export interface FilenameDetection {
  baseModel: string;
  modelType: ModelType | null;
}

export function detectFromFilename(
  filename: string,
  keywords: FilenameKeyword[],
): FilenameDetection {
  const lower = filename.toLowerCase();
  let baseModel = '';
  let modelType: ModelType | null = null;

  for (const kw of keywords) {
    if (!lower.includes(kw.keyword)) continue;
    if (!baseModel && kw.base_model) baseModel = kw.base_model;
    if (!modelType && kw.model_type) modelType = kw.model_type as ModelType;
    if (baseModel && modelType) break;
  }

  return { baseModel, modelType };
}
