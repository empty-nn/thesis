import { Button } from "@/components/ui/button";
import { useTheme } from "@/theme/ThemeProvider";

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex gap-2">
      <Button
        size="sm"
        variant={theme === "light" ? "default" : "outline"}
        onClick={() => setTheme("light")}
      >
        Light
      </Button>

      <Button
        size="sm"
        variant={theme === "dark" ? "default" : "outline"}
        onClick={() => setTheme("dark")}
      >
        Dark
      </Button>

      <Button
        size="sm"
        variant={theme === "ocean" ? "default" : "outline"}
        onClick={() => setTheme("ocean")}
      >
        Ocean
      </Button>
    </div>
  );
}

export default ThemeSwitcher;