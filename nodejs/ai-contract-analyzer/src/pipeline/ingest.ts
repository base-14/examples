import { PDFParse } from "pdf-parse";
import type { ChunkData, IngestResult } from "../types/pipeline.ts";

// ~1000 tokens target per chunk; approximating 4 chars per token
const TARGET_CHUNK_CHARS = 4_000;

export async function ingestDocument(
  file: File,
  contractId: string,
  inject?: { disable_chunking_fallback?: boolean },
): Promise<IngestResult> {
  const buffer = new Uint8Array(await file.arrayBuffer());
  let fullText: string;
  let pageCount: number;

  if (file.type === "application/pdf") {
    try {
      const parser = new PDFParse({ data: buffer });
      try {
        const textResult = await parser.getText();
        fullText = textResult.text;
        pageCount = textResult.total;
      } finally {
        await parser.destroy();
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      throw Object.assign(new Error(`PDF parse failed: ${message}`), {
        code: "PARSE_ERROR",
        detail: message,
      });
    }
  } else {
    fullText = new TextDecoder().decode(buffer);
    pageCount = Math.ceil(fullText.length / 3_000);
  }

  const chunks = chunkText(fullText, pageCount, inject?.disable_chunking_fallback);

  return {
    contract_id: contractId,
    filename: file.name,
    page_count: pageCount,
    total_characters: fullText.length,
    chunks,
    full_text: fullText,
  };
}

function chunkText(text: string, pageCount: number, disableChunkingFallback = false): ChunkData[] {
  // Split on section boundaries: double newlines, headings, or numbered sections
  const paragraphs = text
    .split(/\n{2,}|(?=\n[A-Z][A-Z\s]{3,}\n)|(?=\n\d+\.\s)/)
    .map((p) => p.trim())
    .filter((p) => p.length > 50);

  const chunks: ChunkData[] = [];
  let current = "";
  let chunkIndex = 0;
  const charsPerPage = pageCount > 0 ? text.length / pageCount : text.length;

  const flushChunk = (text: string) => {
    const startChar = chunks.reduce((sum, c) => sum + c.character_count, 0);
    const endChar = startChar + text.length;
    const pageStart = Math.floor(startChar / charsPerPage) + 1;
    const pageEnd = Math.min(Math.ceil(endChar / charsPerPage), pageCount) || 1;

    chunks.push({
      index: chunkIndex++,
      text: text.trim(),
      page_start: pageStart,
      page_end: pageEnd,
      character_count: text.trim().length,
    });
    current = "";
  };

  for (const para of paragraphs) {
    if (current.length + para.length > TARGET_CHUNK_CHARS && current.length > 0) {
      flushChunk(current);
    }
    current += (current ? "\n\n" : "") + para;
  }

  if (current.trim().length > 0) {
    flushChunk(current);
  }

  // Warn when document is very large — chunked extraction degrades accuracy
  if (!disableChunkingFallback && text.length > 600_000) {
    console.warn(
      `[ingest] Document is ${text.length} chars (>${Math.round(text.length / 4)} tokens). ` +
        "Exceeds Claude 200K context — extraction will use chunked mode with reduced accuracy.",
    );
  }

  return chunks;
}
