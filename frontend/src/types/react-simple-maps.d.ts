declare module "react-simple-maps" {
  import { ComponentType, ReactNode, SVGAttributes, MouseEvent } from "react";

  export interface Geography {
    rsmKey: string;
    id: string | number;
    properties: Record<string, unknown>;
    [key: string]: unknown;
  }

  export interface ComposableMapProps {
    projectionConfig?: Record<string, unknown>;
    style?: React.CSSProperties;
    children?: ReactNode;
  }

  export interface ZoomableGroupProps {
    zoom?: number;
    children?: ReactNode;
  }

  export interface GeographiesProps {
    geography: string | Record<string, unknown>;
    children: (args: { geographies: Geography[] }) => ReactNode;
  }

  export interface GeographyProps extends SVGAttributes<SVGPathElement> {
    geography: Geography;
    style?: {
      default?: React.CSSProperties;
      hover?: React.CSSProperties;
      pressed?: React.CSSProperties;
    };
    onMouseEnter?: (e: MouseEvent<SVGPathElement>) => void;
    onMouseMove?: (e: MouseEvent<SVGPathElement>) => void;
    onMouseLeave?: (e: MouseEvent<SVGPathElement>) => void;
  }

  export const ComposableMap: ComponentType<ComposableMapProps>;
  export const ZoomableGroup: ComponentType<ZoomableGroupProps>;
  export const Geographies: ComponentType<GeographiesProps>;
  export const Geography: ComponentType<GeographyProps>;
}