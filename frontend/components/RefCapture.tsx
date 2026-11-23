"use client";

import { useEffect } from "react";
import { captureRefFromUrl } from "@/lib/ref";

/** Невидимый компонент: при заходе на любую страницу запоминает `?ref=CODE`. */
export default function RefCapture() {
  useEffect(() => {
    captureRefFromUrl();
  }, []);
  return null;
}
