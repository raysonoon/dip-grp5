export default function FoodieAvatar({ speaking = false, large = false, waving = false }: {
  speaking?: boolean;
  large?: boolean;
  waving?: boolean;
}) {
  return (
    <span className={`foodie-avatar ${large ? "foodie-avatar-large" : ""} ${speaking ? "foodie-avatar-speaking" : ""} ${waving ? "foodie-avatar-waving" : ""}`} aria-hidden="true">
      <img src={large ? "/ntummy_mascot.svg" : "/ntummy_mascot_head.svg"} alt="" />
    </span>
  );
}
