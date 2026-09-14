export function clearFileInput(input: { value: string } | null): void {
  if (input) {
    input.value = "";
  }
}
