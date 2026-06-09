// src/api/dataBuildingApi.ts

import { axiosClient } from "./axiosClient";

export type PdfConvertMethod = "pymupdf" | "docling";
export type HtmlConvertMethod =    | "trafilatura"
  | "readability"
  | "justext"
  | "boilerpy3"
  | "inscriptis";

export async function convertPdfUpload(
  file: File,
  method: PdfConvertMethod
) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("method", method);

  const response = await axiosClient.post("/convert-pdf-upload", formData);

  return response.data;
}

export async function convertHtmlUrl(
  url: string,
  method: HtmlConvertMethod
) {
  const response = await axiosClient.post("/convert-html-url", {
    url,
    method,
  });

  return response.data;
}

export async function cleanMarkdown(md: string) {
  const response = await axiosClient.post("/clean-markdown", {
    md,
    keep_picture_text: true,
    min_picture_text_chars: 80,
    separate_picture_text: true,
  });
  return response.data;
}