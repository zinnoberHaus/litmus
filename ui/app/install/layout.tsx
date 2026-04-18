import { InstallTabs } from "@/components/InstallTabs";

export const metadata = {
  title: "Install Litmus",
  description:
    "Install paths for Litmus — dbt package first, standalone CLI second, self-hosted third.",
};

export default function InstallLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">
          Install Litmus
        </h1>
        <p className="mt-2 max-w-2xl text-neutral-600">
          Pick the path that matches how your team already ships data. The dbt
          package is the fastest — five-line <code>packages.yml</code> edit
          and you have trust checks firing on every <code>dbt run</code>.
        </p>
      </div>
      <div className="mb-8">
        <InstallTabs />
      </div>
      {children}
    </div>
  );
}
