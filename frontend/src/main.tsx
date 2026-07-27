import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { FeedPage } from "./routes/FeedPage";
import { PainPointsPage } from "./routes/PainPointsPage";
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
            {/* Tabs are kept as far apart as possible: each route excludes what another tab owns,
                so the same insight doesn't show up in three places. Jobs live only in /jobs (and
                /quant-firms, where firm hiring IS the signal). */}
            <Route index element={<FeedPage stream="alpha" excludeItemType="launch,funding,early_stage,hiring" />} />
            <Route path="launches" element={<FeedPage stream="alpha" lockedItemType="launch,funding,early_stage" />} />
            <Route path="jobs" element={<FeedPage stream="alpha" lockedItemType="hiring" />} />
            <Route path="quant-firms" element={<FeedPage stream="alpha" lockedCategory="Quant Firms" />} />
            <Route path="india" element={<FeedPage lockedRegion="India" excludeItemType="hiring" />} />
            <Route path="community" element={<FeedPage stream="community" />} />
            <Route path="pain-points" element={<PainPointsPage />} />
            <Route path="newsletter" element={<NewsletterPage />} />
            <Route path="newsletter/:date" element={<NewsletterPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
