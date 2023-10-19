from src.environment_builder import build_cross_env
from src.planner import a_star_search
from src.visualizer import EnvironmentVisualizer


def main():
    env = build_cross_env()
    paths = a_star_search(env)
    visualizer = EnvironmentVisualizer(800, 800, env, paths)
    visualizer.run()


if __name__ == "__main__":
    main()
