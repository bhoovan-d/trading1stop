import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { FeedPage } from "./routes/FeedPage";
import { NewsletterPage } from "./routes/NewsletterPage";
import "@fontsource-variable/fraunces";
import "@fontsource-variable/inter";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<FeedPage stream="alpha" />} />
            <Route path="quant-firms" element={<FeedPage lockedCategory="Quant Firms" />} />
            <Route path="india" element={<FeedPage lockedRegion="India" />} />
            <Route path="community" element={<FeedPage stream="community" />} />
            <Route path="newsletter" element={<NewsletterPage />} />
            <Route path="newsletter/:date" element={<NewsletterPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
