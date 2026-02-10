import Hero from "@/components/Hero";
import Features from "@/components/Features";
import ChannelsGrid from "@/components/ChannelsGrid";
import ProvidersGrid from "@/components/ProvidersGrid";
import PricingTable from "@/components/PricingTable";
import CTASection from "@/components/CTASection";
import Footer from "@/components/Footer";

export default function Home() {
  return (
    <main>
      <Hero />
      <Features />
      <ChannelsGrid />
      <ProvidersGrid />
      <PricingTable />
      <CTASection />
      <Footer />
    </main>
  );
}
