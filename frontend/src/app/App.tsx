import { useState } from "react";
import { RouterProvider } from "react-router-dom";
import { Providers } from "./providers";
import { createAppRouter } from "./router";

export default function App() {
  const [router] = useState(createAppRouter);
  return <Providers><RouterProvider router={router} /></Providers>;
}
