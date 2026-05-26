# Surface Area of a Sphere: An Integral Derivation

#### Abstract

We derive the surface area of a sphere of radius r from first principles using a double integral in spherical coordinates. The result, 4πr<sup>2</sup> , is obtained by integrating a surface area element over the full range of angular coordinates. This derivation illustrates how calculus can be used to compute geometric quantities that are otherwise difficult to obtain by purely geometric means.

## 1 Introduction and Motivation

The surface area of a sphere is one of the most fundamental results in geometry. While the formula A = 4πr<sup>2</sup> is well known, its proof requires more than simple geometry. The challenge is that a sphere is a curved surface, and measuring curved surfaces requires the tools of integral calculus.

The central problem is: how do we add up infinitely many infinitely small patches of a curved surface to get a total area? Prior to calculus, this result was known to Archimedes, who proved it using exhaustion arguments. The integral approach gives a cleaner and more generalizable method that works for any smooth surface.

## 2 Spherical Coordinates

To describe points on a sphere of radius r, we use spherical coordinates. Every point on the sphere is described by two angles:

- θ the polar angle, measured from the north pole, ranging from 0 to π
- ϕ the azimuthal angle, measured around the equator, ranging from 0 to 2π

In Cartesian coordinates, a point on the sphere is given by:

$$x = r\sin\theta\cos\phi\tag{1}$$

$$y = r\sin\theta\sin\phi\tag{2}$$

$$z = r\cos\theta\tag{3}$$

We can write this as a position vector r(θ, ϕ) = (r sin θ cos ϕ, r sin θ sin ϕ, r cos θ).

#### 3 The Surface Area Element

To integrate over the sphere, we need to know the area of a small patch on the surface corresponding to small changes  $d\theta$  and  $d\phi$ . This is called the *surface area element* dS.

We compute dS by finding two tangent vectors to the sphere and taking the magnitude of their cross product. The tangent vectors are the partial derivatives of  $\mathbf{r}$  with respect to each angle:

$$\frac{\partial \mathbf{r}}{\partial \theta} = (r \cos \theta \cos \phi, \ r \cos \theta \sin \phi, \ -r \sin \theta) \tag{4}$$

$$\frac{\partial \mathbf{r}}{\partial \phi} = (-r\sin\theta\sin\phi, \ r\sin\theta\cos\phi, \ 0) \tag{5}$$

Their cross product is:

$$\frac{\partial \mathbf{r}}{\partial \theta} \times \frac{\partial \mathbf{r}}{\partial \phi} = \left( r^2 \sin^2 \theta \cos \phi, \ r^2 \sin^2 \theta \sin \phi, \ r^2 \sin \theta \cos \theta \right) \tag{6}$$

The magnitude of this cross product gives the surface area element:

$$\left| \frac{\partial \mathbf{r}}{\partial \theta} \times \frac{\partial \mathbf{r}}{\partial \phi} \right| = r^2 \sin \theta \tag{7}$$

Therefore:

$$dS = r^2 \sin\theta \, d\theta \, d\phi \tag{8}$$

The factor  $\sin \theta$  is crucial. It accounts for the fact that patches near the poles ( $\theta \approx 0$  or  $\theta \approx \pi$ ) are smaller than patches near the equator ( $\theta \approx \pi/2$ ), even for the same angular change  $d\theta$ .

## 4 Computing the Integral

The total surface area is obtained by integrating dS over all angles:

$$A = \iint dS = \int_0^{2\pi} \int_0^{\pi} r^2 \sin\theta \, d\theta \, d\phi \tag{9}$$

Since the integrand factors into a  $\theta$ -part and a  $\phi$ -part, we can separate:

$$A = r^2 \left( \int_0^{\pi} \sin \theta \, d\theta \right) \left( \int_0^{2\pi} d\phi \right) \tag{10}$$

The inner integral over  $\theta$ :

$$\int_0^{\pi} \sin \theta \, d\theta = \left[ -\cos \theta \right]_0^{\pi} = -\cos \pi + \cos 0 = 1 + 1 = 2 \tag{11}$$

The outer integral over  $\phi$ :

$$\int_0^{2\pi} d\phi = 2\pi \tag{12}$$

Combining:

$$A = r^2 \cdot 2 \cdot 2\pi = 4\pi r^2$$

$$\tag{13}$$

#### 5 Results and Discussion

We have derived that the surface area of a sphere of radius r is  $A = 4\pi r^2$ , confirming the classical formula through a rigorous integral calculation.

Three things make this derivation work:

- 1. Spherical coordinates naturally parametrize the sphere with just two angles
- 2. The  $\sin \theta$  factor in dS correctly accounts for the varying size of surface patches at different latitudes
- 3. The double integral adds up all patches over the entire surface without overcounting

A key observation: the result does not depend on  $\phi$  at all. The sphere has perfect rotational symmetry around the z-axis, so the  $\phi$  integral simply contributes a factor of  $2\pi$ . If we were computing the surface area of a shape without this symmetry, the  $\phi$  integral would be more involved.

### 6 Limitations and Extensions

This derivation assumes the sphere is perfectly round with constant radius r. It does not apply directly to ellipsoids or other curved surfaces, which require a more general surface integral formula.

The same technique generalizes: to find the surface area of any smooth surface  $\mathbf{r}(u, v)$ , compute:

$$A = \iint \left| \frac{\partial \mathbf{r}}{\partial u} \times \frac{\partial \mathbf{r}}{\partial v} \right| \, du \, dv \tag{14}$$

This is the foundation of differential geometry and applies to surfaces as varied as tori, paraboloids, and minimal surfaces. The sphere derivation is the cleanest special case.