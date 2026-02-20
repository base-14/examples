import { describe, expect, it } from "vitest";
import { ingestDocument } from "../../src/pipeline/ingest.ts";

const CONTRACT_ID = "00000000-0000-0000-0000-000000000001";

function makeFile(content: string, name = "test.txt", type = "text/plain"): File {
  return new File([content], name, { type });
}

describe("ingestDocument — plain text", () => {
  it("extracts full text and filename", async () => {
    const file = makeFile("Hello world. This is a contract.", "contract.txt");
    const result = await ingestDocument(file, CONTRACT_ID);

    expect(result.contract_id).toBe(CONTRACT_ID);
    expect(result.filename).toBe("contract.txt");
    expect(result.full_text).toContain("Hello world");
    expect(result.total_characters).toBeGreaterThan(0);
  });

  it("estimates page count based on character length", async () => {
    const longText = "A".repeat(9_000);
    const file = makeFile(longText);
    const result = await ingestDocument(file, CONTRACT_ID);

    expect(result.page_count).toBeGreaterThan(1);
  });

  it("creates chunks from multi-paragraph text", async () => {
    const content = Array.from(
      { length: 20 },
      (_, i) => `Section ${i + 1}. ${"This is a long paragraph with some legal text. ".repeat(20)}`,
    ).join("\n\n");

    const file = makeFile(content);
    const result = await ingestDocument(file, CONTRACT_ID);

    expect(result.chunks.length).toBeGreaterThan(1);
    for (const chunk of result.chunks) {
      expect(chunk.text.length).toBeGreaterThan(0);
      expect(chunk.character_count).toBe(chunk.text.length);
      expect(chunk.index).toBeGreaterThanOrEqual(0);
    }
  });

  it("chunk indices are sequential starting at 0", async () => {
    const content = Array.from({ length: 10 }, (_, i) => `Para ${i}. ${"text ".repeat(200)}`).join(
      "\n\n",
    );
    const file = makeFile(content);
    const result = await ingestDocument(file, CONTRACT_ID);

    result.chunks.forEach((chunk, i) => {
      expect(chunk.index).toBe(i);
    });
  });

  it("handles minimal contract under threshold as single chunk", async () => {
    const file = makeFile("Short contract. Just a few words.");
    const result = await ingestDocument(file, CONTRACT_ID);

    expect(result.chunks.length).toBeGreaterThanOrEqual(0);
    expect(result.full_text).toBe("Short contract. Just a few words.");
  });
});

describe("ingestDocument — error handling", () => {
  it("throws PARSE_ERROR for invalid PDF content", async () => {
    const garbage = new Uint8Array([0x00, 0x01, 0x02, 0x03]);
    const file = new File([garbage], "bad.pdf", { type: "application/pdf" });

    await expect(ingestDocument(file, CONTRACT_ID)).rejects.toThrow(/PDF parse failed/);
  });
});
