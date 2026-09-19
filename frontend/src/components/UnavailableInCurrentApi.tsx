import { FLASK_UNAVAILABLE_MESSAGE, isFlaskUnavailableError } from "../lib/api";

type UnavailableInCurrentApiProps = {
  className?: string;
};

export function UnavailableInCurrentApi({ className = "" }: UnavailableInCurrentApiProps) {
  return (
    <p className={`text-body text-muted ${className}`.trim()} role="status">
      {FLASK_UNAVAILABLE_MESSAGE}
    </p>
  );
}

type FlaskQueryErrorProps = {
  error: unknown;
  fallback: string;
  className?: string;
};

export function FlaskQueryError({ error, fallback, className = "" }: FlaskQueryErrorProps) {
  if (isFlaskUnavailableError(error)) {
    return <UnavailableInCurrentApi className={className} />;
  }
  return <p className={`text-body text-rose-600 ${className}`.trim()}>{fallback}</p>;
}
