import lion from "../assets/foodie-lion.png";

export default function FoodieAvatar({ speaking = false, large = false, waving = false }: {
  speaking?: boolean;
  large?: boolean;
  waving?: boolean;
}) {
  return (
    <span className={`foodie-avatar ${large ? "foodie-avatar-large" : ""} ${speaking ? "foodie-avatar-speaking" : ""} ${waving ? "foodie-avatar-waving" : ""}`} aria-hidden="true">
      <img src={lion} alt="" />
    </span>
  );
}
