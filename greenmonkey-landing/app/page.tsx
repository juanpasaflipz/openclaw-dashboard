import Hero from "@/components/Hero";
import ProblemSection from "@/components/ProblemSection";
import HowItWorks from "@/components/HowItWorks";
import GitHubAgent from "@/components/GitHubAgent";
import TrustSection from "@/components/TrustSection";
import OpenCore from "@/components/OpenCore";
import Footer from "@/components/Footer";

export default function Home() {
  return (
    <main>
      <Hero />
      <ProblemSection />
      <HowItWorks />
      <GitHubAgent />
      <TrustSection />
      <OpenCore />
      <Footer />
    </main>
  );
}
