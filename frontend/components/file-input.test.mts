import assert from "node:assert/strict";
import test from "node:test";

import { clearFileInput } from "./file-input.ts";

test("permite volver a seleccionar el mismo archivo después de quitarlo", () => {
  const input = { value: "C:\\fakepath\\factura.pdf" };

  clearFileInput(input);

  assert.equal(input.value, "");
});
